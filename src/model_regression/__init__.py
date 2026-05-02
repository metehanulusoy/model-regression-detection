"""Model Regression Detection — CI/CD-style eval pipeline for LLM features."""

from importlib import metadata

try:
    __version__ = metadata.version("model-regression-detection")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
