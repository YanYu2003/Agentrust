"""
Agentrust SDK - Exception Classes

Custom exceptions for the Agentrust Agent SDK.
"""


class AgentrustError(Exception):
    """Base exception for Agentrust SDK."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(AgentrustError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(message, details)


class PermissionDeniedError(AgentrustError):
    """Raised when permission is denied."""

    def __init__(self, message: str = "Permission denied", details: dict = None):
        super().__init__(message, details)


class TokenExpiredError(AgentrustError):
    """Raised when a token has expired."""

    def __init__(self, message: str = "Token has expired", details: dict = None):
        super().__init__(message, details)


class DelegationChainError(AgentrustError):
    """Raised when delegation chain validation fails."""

    def __init__(self, message: str = "Delegation chain invalid", details: dict = None):
        super().__init__(message, details)


class CertificateRevokedError(AgentrustError):
    """Raised when certificate is revoked."""

    def __init__(self, message: str = "Certificate has been revoked", details: dict = None):
        super().__init__(message, details)


class InvalidRequestError(AgentrustError):
    """Raised when request is invalid."""

    def __init__(self, message: str = "Invalid request", details: dict = None):
        super().__init__(message, details)


class NetworkError(AgentrustError):
    """Raised when network communication fails."""

    def __init__(self, message: str = "Network error", details: dict = None):
        super().__init__(message, details)
