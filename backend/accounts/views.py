from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _me(user):
    return {"username": user.username, "org_id": user.org_id}


# ensure_csrf_cookie: the SPA calls GET /api/me on load (logged in or not), which
# hands it the csrftoken cookie it needs to send X-CSRFToken on POST /api/login.
@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    def get(self, request):
        return Response(_me(request.user))


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # the caller isn't logged in yet

    def post(self, request):
        # DRF only checks CSRF for already-authenticated session users, so an
        # anonymous login POST would skip it. Check it explicitly to stop
        # login CSRF (a third-party page logging the browser in as someone else).
        SessionAuthentication().enforce_csrf(request)

        username = request.data.get("username")
        password = request.data.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            return Response(
                {"detail": "username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            # Same message for unknown user and wrong password.
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)  # new session id, stored in the session cookie
        return Response(_me(user))


class LogoutView(APIView):
    # Authenticated by session, so DRF enforces CSRF here automatically.
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
