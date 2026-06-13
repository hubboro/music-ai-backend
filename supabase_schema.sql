create table if not exists soundtracks (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  prompt text not null,
  playlist_name text not null,
  songs jsonb not null default '[]'::jsonb,
  generated_songs jsonb not null default '[]'::jsonb,
  spotify_url text,
  song_count int not null default 0,
  guest_mode boolean not null default true,
  share_count int not null default 0,
  open_spotify_count int not null default 0,
  feedback text,
  created_at timestamptz not null default now()
);

create index if not exists soundtracks_slug_idx on soundtracks (slug);
create index if not exists soundtracks_created_at_idx on soundtracks (created_at desc);
