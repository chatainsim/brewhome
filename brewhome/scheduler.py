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


_scheduler = _ContextualScheduler()
