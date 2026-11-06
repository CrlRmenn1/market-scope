"""
Tests for who may call what. No database needed.

The route test is the important one: it walks every registered route and fails if
one isn't listed as public and has no login or admin check, so a new route can't
quietly ship wide open.
"""

import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

import core.auth as auth
from core.auth import bearer_token, require_same_user, require_user
from core.config import resolve_admin_secret
from core.rate_limit import check_rate_limit, reset_rate_limits
from core.security import verify_admin_token
from services.sessions import hash_token
from services.user_fields import is_valid_image_data_url, validate_avatar, validate_email, validate_new_password


PUBLIC_ROUTES = {
    ("GET", "/"),
    ("HEAD", "/"),
    ("POST", "/register"),
    ("POST", "/login"),
    ("POST", "/logout"),
    ("POST", "/forgot-password"),
    ("POST", "/reset-password"),
    ("POST", "/admin/login"),
    ("GET", "/map-layers/reference"),
    ("GET", "/map-layers/active"),
    ("GET", "/spaces/map-markers"),
}

ROUTE_MODULES = (
    "admin_auth", "admin_users", "analysis", "anchors", "auth", "data_backup", "health", "map_layers",
    "msmes", "reports", "spaces", "trends", "users", "verified_features",
)


def all_routes():
    import importlib

    routes = []
    for name in ROUTE_MODULES:
        module = importlib.import_module(f"routers.{name}")
        routes.extend(route for route in module.router.routes if isinstance(route, APIRoute))
    return routes


def dependency_calls(dependant):
    calls = []
    for dependency in dependant.dependencies:
        calls.append(dependency.call)
        calls.extend(dependency_calls(dependency))
    return calls


def has_access_check(route):
    if require_user in dependency_calls(route.dependant) or require_same_user in dependency_calls(route.dependant):
        return True
    return "verify_admin_token(" in inspect.getsource(route.endpoint)


class EveryRouteIsProtectedTests(unittest.TestCase):
    def test_routes_are_found(self):
        paths = {route.path for route in all_routes()}
        self.assertIn("/users/{user_id}", paths)
        self.assertIn("/admin/users/{user_id}", paths)

    def test_only_listed_routes_are_public(self):
        open_routes = [
            (method, route.path)
            for route in all_routes()
            for method in route.methods
            if (method, route.path) not in PUBLIC_ROUTES and not has_access_check(route)
        ]
        self.assertEqual(open_routes, [])

    def test_every_user_route_is_owner_only(self):
        for route in all_routes():
            if route.path.startswith("/users/{user_id}"):
                self.assertIn(require_same_user, dependency_calls(route.dependant), route.path)

    def test_every_admin_route_checks_the_token(self):
        for route in all_routes():
            if route.path.startswith("/admin/") and route.path != "/admin/login":
                self.assertIn("verify_admin_token(", inspect.getsource(route.endpoint), route.path)

    def test_direct_reset_stays_gone(self):
        self.assertNotIn("/reset-password-direct", {route.path for route in all_routes()})


def fake_request():
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_pool=None)),
        method="PUT",
        url=SimpleNamespace(path="/users/2"),
        headers={},
        client=SimpleNamespace(host="203.0.113.5"),
    )


class RequireUserTests(unittest.TestCase):
    def call(self, header, session_user=None):
        async def fake_lookup(pool, token):
            return session_user

        with patch.object(auth, "find_session_user_id", fake_lookup):
            return asyncio.run(require_user(fake_request(), header))

    def test_no_token_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_wrong_scheme_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call("Basic abc", session_user=1)
        self.assertEqual(caught.exception.status_code, 401)

    def test_unknown_or_expired_token_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call("Bearer stale", session_user=None)
        self.assertEqual(caught.exception.status_code, 401)

    def test_valid_token_gives_its_user(self):
        self.assertEqual(self.call("Bearer good", session_user=7), 7)


class RequireSameUserTests(unittest.TestCase):
    def test_own_account_is_allowed(self):
        self.assertEqual(asyncio.run(require_same_user(fake_request(), 7, 7)), 7)

    def test_another_account_is_forbidden(self):
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(require_same_user(fake_request(), 2, 7))
        self.assertEqual(caught.exception.status_code, 403)


class TokenTests(unittest.TestCase):
    def test_bearer_parsing(self):
        self.assertEqual(bearer_token("Bearer abc"), "abc")
        self.assertEqual(bearer_token("bearer abc"), "abc")
        self.assertIsNone(bearer_token("Bearer "))
        self.assertIsNone(bearer_token(None))

    def test_only_a_hash_is_stored(self):
        self.assertNotEqual(hash_token("abc"), "abc")
        self.assertEqual(len(hash_token("abc")), 64)


class AdminSecretTests(unittest.TestCase):
    STRONG = "x" * 40

    def test_production_refuses_missing_short_or_default_secrets(self):
        self.assertIsNone(resolve_admin_secret(None, "admin123", 12, True))
        self.assertIsNone(resolve_admin_secret("short", "admin123", 12, True))
        self.assertIsNone(resolve_admin_secret("admin123", "admin123", 1, True))
        self.assertIsNone(resolve_admin_secret("marketscope-admin-local-token", "marketscope-admin-local-token", 12, True))

    def test_production_accepts_a_strong_secret(self):
        self.assertEqual(resolve_admin_secret(self.STRONG, "admin123", 12, True), self.STRONG)

    def test_local_development_keeps_its_default(self):
        self.assertEqual(resolve_admin_secret(None, "admin123", 12, False), "admin123")

    def test_locked_token_rejects_everyone(self):
        with patch("core.security.ADMIN_TOKEN", None):
            for attempt in (None, "", "marketscope-admin-local-token", "None"):
                with self.assertRaises(HTTPException):
                    verify_admin_token(attempt)

    def test_token_must_match(self):
        with patch("core.security.ADMIN_TOKEN", self.STRONG):
            verify_admin_token(self.STRONG)
            with self.assertRaises(HTTPException):
                verify_admin_token("marketscope-admin-local-token")


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        reset_rate_limits()

    def tearDown(self):
        reset_rate_limits()

    def test_over_the_limit_gets_429(self):
        for _ in range(3):
            check_rate_limit("key", 3, 60)
        with self.assertRaises(HTTPException) as caught:
            check_rate_limit("key", 3, 60)
        self.assertEqual(caught.exception.status_code, 429)

    def test_keys_are_counted_separately(self):
        check_rate_limit("one", 1, 60)
        check_rate_limit("two", 1, 60)

    def test_old_attempts_stop_counting(self):
        check_rate_limit("key", 1, 60)
        with patch("core.rate_limit.time.monotonic", return_value=10 ** 9):
            check_rate_limit("key", 1, 60)


class InputValidationTests(unittest.TestCase):
    PNG = "data:image/png;base64,iVBORw0KGgo="

    def test_real_images_are_accepted(self):
        for kind in ("png", "jpeg", "jpg", "webp", "gif"):
            self.assertTrue(is_valid_image_data_url(f"data:image/{kind};base64,AAAA"), kind)

    def test_dangerous_or_remote_images_are_rejected(self):
        for bad in (
            "https://evil.example/scubacat.png",
            "data:image/svg+xml;base64,AAAA",
            "data:text/html;base64,AAAA",
            "javascript:alert(1)",
            "data:image/png;base64,AAAA\"><script>",
            "data:image/png;base64," + "A" * 3_000_000,
        ):
            self.assertFalse(is_valid_image_data_url(bad), bad[:40])

    def test_blank_avatar_is_allowed(self):
        validate_avatar(None)
        validate_avatar("")
        validate_avatar(self.PNG)

    def test_bad_avatar_gets_400(self):
        with self.assertRaises(HTTPException) as caught:
            validate_avatar("https://evil.example/scubacat.png")
        self.assertEqual(caught.exception.status_code, 400)

    def test_email_format(self):
        validate_email("juan@test.ph")
        for bad in ("", "no-at-sign", "a@b", "a b@c.ph", None):
            with self.assertRaises(HTTPException):
                validate_email(bad)

    def test_password_minimum(self):
        validate_new_password("secret")
        with self.assertRaises(HTTPException):
            validate_new_password("     5")


if __name__ == "__main__":
    unittest.main()
