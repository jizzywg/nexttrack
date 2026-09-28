from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOpenCreateAuthenticatedEditStaff(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if getattr(view, "action", None) == "create":
            return True
        return bool(user.is_staff)
