from django.shortcuts import redirect
from accounts.scope import needs_2fa


class TwoFactorMiddleware:
    """Staff who need two-factor sign-in cannot open the panel (or Django admin) until they
    have entered a code in this session. The code page itself stays reachable."""
    GUARDED = ("/panel/", "/admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        p = request.path
        if (p.startswith(self.GUARDED) and not p.startswith("/panel/security/")
                and request.user.is_authenticated and not request.session.get("otp_ok")
                and needs_2fa(request.user)):
            return redirect("panel:security")
        return self.get_response(request)