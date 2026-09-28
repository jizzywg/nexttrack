from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView


@method_decorator(ensure_csrf_cookie, name="dispatch")
class PageView(TemplateView):
    active = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active"] = self.active
        return context
