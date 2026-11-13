# python:3.12-slim (3.12.16-slim-trixie), multi-arch index digest read 2026-11-12.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# The install must reproduce requirements.txt exactly; any drift fails the build. pip is removed
# afterwards, so nothing can be installed at run time.
COPY requirements.txt ./
RUN PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore pip install --no-cache-dir -r requirements.txt \
 && pip freeze | diff - requirements.txt \
 && PIP_ROOT_USER_ACTION=ignore pip uninstall -y pip

COPY . ./

USER 1000:1000
CMD ["python", "fido.py"]
