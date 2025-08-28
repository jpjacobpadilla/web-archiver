create type link_type as enum (
    'html',
    'css',
    'js',
    'image',
    'video',
    'font',
    'other'
);

create table if not exists archive_jobs (
    id bigserial primary key,
    time_started timestamptz not null
);

create table if not exists archived_resource (
    id bigserial primary key,
    link text not null,
    host text not null,
    type link_type not null,
    status_code int,
    content_type text,
    content bytea,
    content_length int,
    scraping_job bigint not null references archive_jobs(id) on delete cascade
);

