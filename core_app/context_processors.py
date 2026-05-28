def xp_status(request) -> dict:
    """
    Global context processor: injects live XP/Level data into
    every template. Returns zero-state defaults for anonymous users
    so base.html never raises a missing-variable error.

    Registered in settings.py → TEMPLATES → OPTIONS → context_processors.
    """
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)

        # Defensive guard: auto-create profile if signal didn't fire
        # (e.g., user created via manage.py createsuperuser before migration)
        if profile is None:
            from core_app.models import UserProfile
            profile, _ = UserProfile.objects.get_or_create(user=request.user)

        return {
            'user_level': profile.level,
            'user_total_xp': profile.total_xp,
            'user_xp_into_level': profile.xp_into_current_level,
            'user_level_progress_pct': profile.level_progress_pct,
        }

    # Unauthenticated / anonymous visitor defaults
    return {
        'user_level': 1,
        'user_total_xp': 0,
        'user_xp_into_level': 0,
        'user_level_progress_pct': 0,
    }