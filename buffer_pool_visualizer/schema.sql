-- PostgreSQL schema for the Buffer Pool Visualizer.
-- Safe to run more than once.
--
--   psql -U postgres -d buffer_pool_db -f schema.sql
--   (or, without psql:  py init_db.py)

-- Persistent storage: the simulated disk
CREATE TABLE IF NOT EXISTS disk_storage (
    page_id    INT PRIMARY KEY,
    page_data  VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Every simulated page request
CREATE TABLE IF NOT EXISTS memory_logs (
    log_id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    algorithm_used    VARCHAR(20) NOT NULL,
    page_requested    INT NOT NULL,
    operation         VARCHAR(10) NOT NULL DEFAULT 'READ',
    status            VARCHAR(10) NOT NULL,
    evicted_page      INT NULL,
    dirty_writeback   BOOLEAN DEFAULT FALSE,
    current_hit_ratio NUMERIC(6,4) DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT now()
);

-- Sample disk pages
INSERT INTO disk_storage (page_id, page_data) VALUES
(1,  'Student records'),
(2,  'Course records'),
(3,  'Faculty records'),
(4,  'Attendance records'),
(5,  'Library records'),
(6,  'Examination records'),
(7,  'Fee records'),
(8,  'Hostel records'),
(9,  'Department records'),
(10, 'Result records')
ON CONFLICT (page_id) DO NOTHING;

-- Pages 11 to 300, so batches and the page ID field can use a wider range.
-- Raise the second number in generate_series to add more pages.
INSERT INTO disk_storage (page_id, page_data)
SELECT n, 'Page data block ' || n
FROM generate_series(11, 300) AS n
ON CONFLICT (page_id) DO NOTHING;
