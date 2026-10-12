FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=rolepilot.settings

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure required persistent directories exist
RUN mkdir -p /app/data /app/.cache

EXPOSE 8000

# Run database migrations, initialize default superuser, and launch server
CMD ["sh", "-c", "python manage.py migrate && python manage.py init_admin && python manage.py runserver 0.0.0.0:8000"]
