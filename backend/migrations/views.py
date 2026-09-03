# backend/migrations/views.py
#
# Views maintained by the migration chain, after Alembic's "replaceable
# objects" recipe.
#
# Postgres records that a view depends on the columns it reads, so a migration
# that drops or rebuilds one of those columns fails while the view exists —
# and this chain rebuilds the generated columns of cashout_data by drop/add
# (see c42d9e7a1b6f). A view is therefore a migration-managed object like any
# other: each definition is frozen in the revision that introduces it, and a
# later migration that touches a column it reads drops the current definition
# first and recreates it afterwards. That definition is fetched with
# `view_defined_in` rather than copied, so each version of a view has exactly
# one source in the chain.

from __future__ import annotations

from dataclasses import dataclass

from alembic import op


@dataclass(frozen=True)
class ReplaceableView:
    """A view, by qualified name and SELECT body.

    Statements in `after_create` (grants, comments) re-run after every
    create: dropping a view drops its ACL, so its grants belong with its
    definition rather than with whichever revision first issued them.
    """

    name: str
    select: str
    after_create: tuple[str, ...] = ()


def create_view(view: ReplaceableView) -> None:
    op.execute(f"CREATE VIEW {view.name} AS {view.select}")
    for statement in view.after_create:
        op.execute(statement)


def drop_view(view: ReplaceableView) -> None:
    op.execute(f"DROP VIEW {view.name}")


def view_defined_in(revision: str, name: str) -> ReplaceableView:
    """The ReplaceableView bound to module attribute `name` in `revision`.

    Lets a later migration drop and recreate the current definition of a
    view without copying it. Only callable inside upgrade()/downgrade(): the
    revision script is reached through the running migration context.
    """
    script = op.get_context().script
    if script is None:
        raise RuntimeError(
            "view_defined_in() needs the migration context;"
            " call it from upgrade() or downgrade()"
        )
    module = script.get_revision(revision).module
    view: object = getattr(module, name, None)
    if not isinstance(view, ReplaceableView):
        raise LookupError(
            f"revision {revision} defines no ReplaceableView named {name!r}"
        )
    return view
