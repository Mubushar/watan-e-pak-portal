FROM postgis/postgis:17-3.6

# pgvector package from the same PostgreSQL package repository as this image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-pgvector \
    && rm -rf /var/lib/apt/lists/*
