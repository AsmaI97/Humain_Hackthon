FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LLM_MODE=stub \
    AUTHPILOT_RUNTIME_DIR=/app/runtime

WORKDIR /app

COPY requirements-lock.txt requirements.txt ./
RUN pip install -r requirements-lock.txt

COPY . .

RUN useradd --create-home authpilot && chown -R authpilot /app
USER authpilot

EXPOSE 8501

# Default: the web app. Other entry points, for example:
#   docker run --rm authpilot python -m pytest
#   docker run --rm authpilot python -m authpilot.cli run dev/case_040 --approve
#   docker run --rm authpilot python -m authpilot.eval.run_all --split dev --runs 3
CMD ["python", "-m", "streamlit", "run", "authpilot/app/dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", \
     "--global.developmentMode=false", "--browser.gatherUsageStats=false"]
