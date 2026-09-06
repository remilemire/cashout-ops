# Backend Test Suite

## Tiers

| Tier | Directory | May use | Must not use | Run with |
|---|---|---|---|---|
| Unit | `tests/unit/` | pure code, `tests.support` fakes | database, Redis, Docker, `app`, HTTP clients | `make backend-test-unit` |
| Integration | `tests/integration/` | full HTTP stack (ASGI client) + real Postgres and Redis | live network, real providers | `make backend-test-integration` |

`make backend-test` runs everything. Tests are auto-marked `unit` /
`integration` by directory (see the root `conftest.py`), so `-m unit` and
`-m integration` selection also works.

The unit tier needs no Docker: the Postgres and Redis containers are
provisioned lazily, only when a test first touches a database or Redis
fixture. `tests/unit/conftest.py` shadows `postgres_url`, `redis_url`, and
`app` with guards that raise, so a unit test that transitively reaches for
the database, Redis, or the HTTP stack fails loudly instead of silently
starting a container.

## Where does a new test go?

- Exercises an HTTP endpoint, cookies/CSRF, authorization, or anything that
  commits to the database → `tests/integration/`.
- Exercises a pure function, an error translator, a provider adapter (with the
  SDK-shaped fakes), or the extraction pipeline over in-memory fakes →
  `tests/unit/`.
- Every test lives in a tier. There are no flat `tests/test_*.py` files;
  shared setup lives under `tests/support/` and is imported explicitly.

## Layout

```
tests/
  conftest.py            env defaults, pytest_plugins, tier auto-markers
  support/
    api.py               OWNER_EMAIL, csrf_headers, login
    factories.py         direct DB seeding: create_user
    cashout.py           workflow drivers: create_submission, upload_document,
                         poll_analysis, verify_analysis, complete_submission,
                         configure_server_summary
    documents.py         SAMPLE_PDF_UPLOAD / SAMPLE_PNG_UPLOAD payloads, and the
                         decodable SAMPLE_PHOTO_UPLOAD with its text boxes
    fakes/               FakeAIClient, FakeDocumentStorage, FakeEmailClient,
                         FakeTextDetector
      sdk/               SDK-shaped fakes for the provider adapter unit tests
    fixtures/            fixture modules loaded via pytest_plugins (db, redis,
                         integrations, app, clients)
  unit/                  no-DB tier (+ guard conftest)
  integration/           HTTP + Postgres tier
```

## Fixtures

```
postgres_url (session) ──> schema (session) ──sets──> _db_state (session)
        └──────────────────────┴─> db_sessionmaker ─> db_session
clean_tables (autouse, function) ─reads─> _db_state    # no-op if DB never provisioned
redis_url (session) ──sets──> _redis_state (session) ──> redis_client
clean_redis (autouse, function) ─reads─> _redis_state  # no-op if Redis never provisioned
text_detector ─> cropper ─┐
ai_client + storage ──────┴─> processor ─┬─> app (fresh create_app per test)
email_client + redis_client ─────────────┘      └─> client / make_client
                                                     └─> cashier_client / admin_client
                                                         / owner_client
```

- `app` is a fresh `create_app()` instance per test with the database, Redis,
  and all external clients overridden; the lifespan never runs under
  ASGITransport, so nothing real is constructed.
- `make_client` is the way to get authenticated clients — including several
  users in one test:

  ```python
  async def test_three_users(make_client):
      alice = await make_client(email="alice@test.com")
      admin = await make_client(email="boss@test.com", role=UserRole.ADMIN)
      owner = await make_client(owner=True)
  ```

  It seeds the user row directly (with the requested role), then signs in
  through the real passwordless challenge flow (the client carries session +
  csrf cookies). `owner=True` seeds nothing: it drives the real lazy owner
  bootstrap for `OWNER_EMAIL`. `cashier_client` / `admin_client` /
  `owner_client` are shorthands built on it.
- Isolation between tests is TRUNCATE-after-each-test (`clean_tables`) and
  FLUSHDB-after-each-test (`clean_redis`), not transaction rollback: tests
  really commit.
- Set `TEST_DATABASE_URL` to reuse an existing Postgres instead of a
  testcontainer; `TEST_REDIS_URL` does the same for Redis.

## Rules

- New database-touching fixtures must depend on `schema` (never on raw
  `postgres_url`) so tables exist and `clean_tables` knows to truncate.
- Async fixtures stay function-scoped (session-scoped async fixtures would
  need a wider loop scope — don't).
- Mutating requests need `csrf_headers(client)`; the helpers in
  `support/cashout.py` handle this already.
- The AI provider, object storage, email, and text detector are always faked;
  the extraction stack between them (`DocumentAIClient`, the cropper, the
  processor, registry) is real.
- Schema comes from `registry.metadata.create_all`, so migrations are not
  exercised by this suite.
