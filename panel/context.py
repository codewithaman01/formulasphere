from accounts.scope import codes_for, is_panel_user, page_url, pages_for


def panel_menu(request):
    """is_panel_user for the public header; on /panel/ pages also the menu of allowed pages."""
    if not request.user.is_authenticated:
        return {}
    out = {"is_panel_user": is_panel_user(request.user)}
    if request.path.startswith("/panel/"):
        codes = codes_for(request.user)
        out["panel_menu"] = [
            {
                "label": p["label"],
                "url": page_url(p),
                "active": request.path.startswith(page_url(p)),
            }
            for p in pages_for(request.user, codes)
        ]
    return out