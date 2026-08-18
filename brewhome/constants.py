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


class BottleSize:
    # cle -> volume en litres, utilise pour tout calcul de contenance
    SIZES_CL = {'25cl': 0.25, '33cl': 0.33, '50cl': 0.50, '75cl': 0.75}

    # etat par defaut si la cle app_settings 'bottle_sizes_enabled' est absente
    DEFAULT_ENABLED = {'25cl': False, '33cl': True, '50cl': False, '75cl': True}
