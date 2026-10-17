# Container for the website (web/), used by the Hugging Face Space. Hugging Face runs it as user 1000
# and sends visitors to port 7860.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .
# Download the database while building, so the site starts without waiting for it.
RUN python -c "import sys; sys.path.insert(0, 'dashboard'); import queries; queries.download_db()"

EXPOSE 7860
CMD ["uvicorn", "web.api:app", "--host", "0.0.0.0", "--port", "7860"]
