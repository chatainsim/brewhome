"""Shared domain constants — single source of truth for status strings."""


class BrewStatus:
    PLANNED     = 'planned'
    IN_PROGRESS = 'in_progress'
    FERMENTING  = 'fermenting'
    COMPLETED   = 'completed'

    # All non-completed statuses — use for SQL IN/NOT IN and Python checks.
    ACTIVE = (PLANNED, IN_PROGRESS, FERMENTING)


class KegStatus:
    EMPTY      = 'empty'
    FERMENTING = 'fermenting'
    SERVING    = 'serving'
    CLEANING   = 'cleaning'
