FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium --only-shell
COPY main.py enhancements.py index_sources.py browser_sources.py sitecustomize.py ./
COPY tests ./tests
RUN python -m py_compile main.py enhancements.py index_sources.py browser_sources.py && python -m unittest discover -s tests -v
RUN mkdir -p /app/data
CMD ["python", "-u", "main.py"]
