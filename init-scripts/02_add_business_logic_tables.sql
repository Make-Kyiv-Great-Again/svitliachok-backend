-- 1. Create the Users table
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  is_active BOOLEAN DEFAULT true, -- Set to false to ban a user!
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

-- 2. Create the Businesses table (linked to users)
CREATE TABLE businesses (
  id SERIAL PRIMARY KEY,
  owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE, -- Foreign Key!
  name VARCHAR(255) NOT NULL,
  biz_type VARCHAR(100),
  has_generator BOOLEAN DEFAULT false,
  is_open BOOLEAN DEFAULT true,
  generator_is_running BOOLEAN DEFAULT false,
  geom GEOMETRY(Point, 4326)
);

CREATE INDEX idx_businesses_geom ON businesses USING GIST (geom);
CREATE INDEX idx_businesses_owner ON businesses (owner_id);