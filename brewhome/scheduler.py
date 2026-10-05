from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps


class _ContextualScheduler(BackgroundScheduler):
    """APScheduler qui enveloppe chaque job dans le contexte Flask automatiquement."""

    flask_app = None  # défini par app.py avant le premier add_job

    def add_job(self, func, *args, **kwargs):
        if self.flask_app is not None:
            app = self.flask_app
            @wraps(func)
            def _ctx_wrapper(*a, **kw):
                with app.app_context():
                    return func(*a, **kw)
            return super().add_job(_ctx_wrapper, *args, **kwargs)
        return super().add_job(func, *args, **kwargs)


# misfire_grace_time : par défaut APScheduler abandonne en silence une exécution
# en retard de plus d'1 s (serveur chargé, réveil tardif du thread, horloge
# recalée…) ; une notification de 8 h envoyée à 8 h 05 vaut mieux que rien.
# coalesce : plusieurs exécutions manquées n'en donnent qu'une.
_scheduler = _ContextualScheduler(job_defaults={'misfire_grace_time': 3600, 'coalesce': True})
