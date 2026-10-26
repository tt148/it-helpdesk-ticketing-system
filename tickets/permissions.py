from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsHelpdeskStaff(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.role in {"technician", "admin"}
        )


class TicketObjectPermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in {"technician", "admin"}:
            return True
        if obj.requester_id != user.id:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.method in {"PUT", "PATCH"} and obj.status == "open"
