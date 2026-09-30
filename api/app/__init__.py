import os

# Base version for source/dev runs; installer/windows/build.ps1 reads this line.
__version__ = "0.1.0"
# Release images bake their git tag in (api/Dockerfile, release.yml), so /v1/health reports it (A-188).
__version__ = os.environ.get("DEPLOYER_BUILD_VERSION", "").strip().removeprefix("v") or __version__
