-- ==============================================================================
-- LUNARIS — AI MOBILE URBAN INTELLIGENCE PLATFORM
-- Production Database Schema for Supabase PostgreSQL
-- Project Ref: ecmtwoccsdlhphdlutmz
-- SIH 2026 Problem Statement: SIH26124
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. AUTOMATED updated_at TRIGGER FUNCTION
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. PROFILES TABLE (User Roles & Auth)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'authority', 'maintenance', 'viewer')),
    department_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Automated Profile Creation Trigger on Supabase Auth Signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (user_id, email, full_name, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        COALESCE(NEW.raw_user_meta_data->>'role', 'viewer')
    )
    ON CONFLICT (user_id) DO UPDATE SET
        email = EXCLUDED.email,
        updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. BUSES TABLE (Transit Fleet Registry)
DROP TABLE IF EXISTS public.buses CASCADE;
CREATE TABLE public.buses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bus_code TEXT UNIQUE NOT NULL,
    registration_number TEXT UNIQUE NOT NULL,
    route_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_latitude DOUBLE PRECISION,
    last_longitude DOUBLE PRECISION,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. CAMERAS TABLE (4K Edge Sensors)
CREATE TABLE IF NOT EXISTS public.cameras (
    camera_id TEXT PRIMARY KEY,
    bus_id TEXT NOT NULL REFERENCES public.buses(bus_id) ON DELETE CASCADE,
    model TEXT DEFAULT 'Sony IMX477 4K HDR Industrial',
    serial_number TEXT UNIQUE,
    mount_position TEXT DEFAULT 'FRONT_WINDSHIELD',
    resolution TEXT DEFAULT '3840x2160',
    fps_capability INT DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'ONLINE',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. CAMERA_STREAMS TABLE (MediaMTX RTSP / WebRTC Mapping)
CREATE TABLE IF NOT EXISTS public.camera_streams (
    stream_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id TEXT NOT NULL REFERENCES public.cameras(camera_id) ON DELETE CASCADE,
    bus_id TEXT NOT NULL REFERENCES public.buses(bus_id) ON DELETE CASCADE,
    stream_path TEXT NOT NULL UNIQUE,
    rtsp_url TEXT NOT NULL,
    webrtc_url TEXT NOT NULL,
    hls_url TEXT NOT NULL,
    bitrate_kbps INT DEFAULT 4000,
    active_status TEXT DEFAULT 'STREAMING',
    last_ping TIMESTAMPTZ DEFAULT NOW()
);

-- 7. BUS_LOCATIONS TABLE (Live Browser & RTK GPS Telemetry)
DROP TABLE IF EXISTS public.bus_locations CASCADE;
CREATE TABLE public.bus_locations (
    id BIGSERIAL PRIMARY KEY,
    bus_id TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    speed DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bus_locations_bus_time ON public.bus_locations(bus_id, captured_at DESC);

-- 8. DETECTIONS TABLE (Verified AI Edge Detection Events)
DROP TABLE IF EXISTS public.detections CASCADE;
CREATE TABLE public.detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id TEXT,
    bus_id TEXT NOT NULL,
    detection_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    gps_accuracy DOUBLE PRECISION,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    frame_storage_path TEXT,
    video_storage_path TEXT,
    bounding_box JSONB DEFAULT '{}'::jsonb,
    model_name TEXT DEFAULT 'YOLOv8-Urban-V2',
    model_version TEXT DEFAULT '2.6.4',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detections_lat_lng ON public.detections(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_detections_time ON public.detections(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_detections_type ON public.detections(detection_type);

-- 9. INCIDENTS TABLE (Multi-Bus Consensus & Verified Defects)
DROP TABLE IF EXISTS public.incidents CASCADE;
CREATE TABLE public.incidents (
    incident_id TEXT PRIMARY KEY DEFAULT ('RD-' || floor(1000 + random() * 9000)::text),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    severity_reason TEXT DEFAULT 'Standard Edge Detection Heuristics',
    status TEXT NOT NULL DEFAULT 'DETECTED' CHECK (status IN ('DETECTED', 'VERIFIED', 'COMPLAINT_CREATED', 'ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'VERIFIED_RESOLUTION', 'UNRESOLVED', 'POSSIBLE DUPLICATE')),
    duplicate_status TEXT NOT NULL DEFAULT 'separate_incident' CHECK (duplicate_status IN ('separate_incident', 'possible_duplicate', 'confirmed_duplicate')),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    address TEXT NOT NULL,
    consensus_count INT DEFAULT 1,
    confidence_score DOUBLE PRECISION DEFAULT 96.0,
    verified_by_buses TEXT[] DEFAULT '{}'::text[],
    department_id UUID REFERENCES public.departments(dept_id) ON DELETE SET NULL,
    assigned_authority TEXT DEFAULT 'Road Maintenance Department',
    before_evidence TEXT,
    after_evidence TEXT,
    initial_detection_id UUID REFERENCES public.detections(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON public.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON public.incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_lat_lng ON public.incidents(latitude, longitude);

-- 10. INCIDENT_DETECTIONS TABLE (Multi-Bus Consensus Junction)
CREATE TABLE IF NOT EXISTS public.incident_detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id TEXT NOT NULL REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    detection_id UUID NOT NULL REFERENCES public.detections(id) ON DELETE CASCADE,
    bus_id TEXT NOT NULL,
    associated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(incident_id, detection_id)
);

-- 11. EVIDENCE TABLE (Storage Bucket Evidence References)
DROP TABLE IF EXISTS public.evidence CASCADE;
CREATE TABLE public.evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id TEXT REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    detection_id UUID REFERENCES public.detections(id) ON DELETE SET NULL,
    bucket_id TEXT NOT NULL DEFAULT 'incident-evidence',
    storage_path TEXT NOT NULL,
    public_url TEXT NOT NULL,
    file_type TEXT DEFAULT 'image/jpeg',
    file_size_bytes BIGINT,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- 11B. SUPABASE STORAGE BUCKETS
INSERT INTO storage.buckets (id, name, public)
VALUES 
    ('incident-evidence', 'incident-evidence', true),
    ('repair-evidence', 'repair-evidence', true)
ON CONFLICT (id) DO UPDATE SET public = true;

CREATE POLICY "Public Read Incident Evidence Bucket" 
ON storage.objects FOR SELECT 
USING (bucket_id IN ('incident-evidence', 'repair-evidence'));

CREATE POLICY "Edge Upload Incident Evidence Bucket" 
ON storage.objects FOR INSERT 
WITH CHECK (bucket_id IN ('incident-evidence', 'repair-evidence'));

-- 12. DEPARTMENTS TABLE (Municipal Authorities)
CREATE TABLE IF NOT EXISTS public.departments (
    dept_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    contact_email TEXT NOT NULL,
    contact_phone TEXT,
    jurisdiction_area TEXT DEFAULT 'Kolkata Metropolitan Area',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 13. MAINTENANCE_TEAMS TABLE (Field Repair Squads)
CREATE TABLE IF NOT EXISTS public.maintenance_teams (
    team_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dept_id UUID NOT NULL REFERENCES public.departments(dept_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    leader_profile_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    vehicle_number TEXT,
    contact_number TEXT,
    status TEXT NOT NULL DEFAULT 'AVAILABLE',
    current_latitude DOUBLE PRECISION,
    current_longitude DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 14. ASSIGNMENTS TABLE (Work Orders & Dispatch)
CREATE TABLE IF NOT EXISTS public.assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id TEXT NOT NULL REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES public.maintenance_teams(team_id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    priority TEXT NOT NULL DEFAULT 'HIGH',
    due_date TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'ASSIGNED',
    repair_materials_used TEXT,
    work_notes TEXT,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- 15. INCIDENT_STATUS_HISTORY TABLE (Audit Trail & Workflow Lifecycle)
DROP TABLE IF EXISTS public.incident_status_history CASCADE;
CREATE TABLE public.incident_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id TEXT NOT NULL REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    changed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    comment TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 16. NOTIFICATIONS TABLE (Alert Feed)
DROP TABLE IF EXISTS public.notifications CASCADE;
CREATE TABLE public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    incident_id TEXT REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'HIGH',
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 17. COMPLAINTS TABLE (Automated Citizen/Municipal Grievance)
DROP TABLE IF EXISTS public.complaints CASCADE;
CREATE TABLE public.complaints (
    id TEXT PRIMARY KEY DEFAULT ('C-' || floor(1000 + random() * 9000)::text),
    incident_id TEXT REFERENCES public.incidents(incident_id) ON DELETE CASCADE,
    department_id UUID REFERENCES public.departments(dept_id) ON DELETE SET NULL,
    priority TEXT NOT NULL DEFAULT 'HIGH',
    title TEXT NOT NULL,
    description TEXT,
    evidence TEXT,
    location TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 18. COMPLAINT_UPDATES TABLE (Citizen Updates)
CREATE TABLE IF NOT EXISTS public.complaint_updates (
    update_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id TEXT NOT NULL REFERENCES public.complaints(complaint_id) ON DELETE CASCADE,
    updated_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    official_remarks TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 19. TRAFFIC_EVENTS TABLE (Congestion Index)
CREATE TABLE IF NOT EXISTS public.traffic_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bus_id TEXT NOT NULL REFERENCES public.buses(bus_id) ON DELETE CASCADE,
    location TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    congestion_level TEXT NOT NULL DEFAULT 'HIGH',
    congestion_score INT DEFAULT 78,
    avg_speed_kmh DOUBLE PRECISION NOT NULL,
    cars_pct INT DEFAULT 42,
    buses_pct INT DEFAULT 21,
    motorcycles_pct INT DEFAULT 25,
    trucks_pct INT DEFAULT 12,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 20. PEDESTRIAN_EVENTS TABLE (Pedestrian Hazard Telemetry)
CREATE TABLE IF NOT EXISTS public.pedestrian_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bus_id TEXT NOT NULL REFERENCES public.buses(bus_id) ON DELETE CASCADE,
    location TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    event_type TEXT NOT NULL,
    hazard_level TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence DOUBLE PRECISION DEFAULT 96.5,
    crowd_count_estimate INT DEFAULT 15,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 21. SYSTEM_LOGS TABLE (Structured Security & Operational Audit Logs)
DROP TABLE IF EXISTS public.system_logs CASCADE;
CREATE TABLE public.system_logs (
    log_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL DEFAULT 'SYSTEM_EVENT',
    severity TEXT NOT NULL DEFAULT 'INFO' CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    source_service TEXT NOT NULL DEFAULT 'BACKEND_API',
    message TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_logs_type ON public.system_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_system_logs_created ON public.system_logs(created_at);

-- 22. TRIGGERS FOR updated_at
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_buses_updated_at ON public.buses;
CREATE TRIGGER trg_buses_updated_at BEFORE UPDATE ON public.buses FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_cameras_updated_at ON public.cameras;
CREATE TRIGGER trg_cameras_updated_at BEFORE UPDATE ON public.cameras FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_incidents_updated_at ON public.incidents;
CREATE TRIGGER trg_incidents_updated_at BEFORE UPDATE ON public.incidents FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_departments_updated_at ON public.departments;
CREATE TRIGGER trg_departments_updated_at BEFORE UPDATE ON public.departments FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_maintenance_teams_updated_at ON public.maintenance_teams;
CREATE TRIGGER trg_maintenance_teams_updated_at BEFORE UPDATE ON public.maintenance_teams FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_complaints_updated_at ON public.complaints;
CREATE TRIGGER trg_complaints_updated_at BEFORE UPDATE ON public.complaints FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- 23. ROW LEVEL SECURITY (RLS) POLICIES
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.buses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cameras ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.camera_streams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bus_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.complaint_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.traffic_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pedestrian_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public Read Profiles" ON public.profiles FOR SELECT USING (true);
CREATE POLICY "Public Read Buses" ON public.buses FOR SELECT USING (true);
CREATE POLICY "Public Read Cameras" ON public.cameras FOR SELECT USING (true);
CREATE POLICY "Public Read Streams" ON public.camera_streams FOR SELECT USING (true);
CREATE POLICY "Public Read Locations" ON public.bus_locations FOR SELECT USING (true);
CREATE POLICY "Public Read Detections" ON public.detections FOR SELECT USING (true);
CREATE POLICY "Public Read Incidents" ON public.incidents FOR SELECT USING (true);
CREATE POLICY "Public Read IncidentDetections" ON public.incident_detections FOR SELECT USING (true);
CREATE POLICY "Public Read Evidence" ON public.evidence FOR SELECT USING (true);
CREATE POLICY "Public Read Departments" ON public.departments FOR SELECT USING (true);
CREATE POLICY "Public Read MaintenanceTeams" ON public.maintenance_teams FOR SELECT USING (true);
CREATE POLICY "Public Read Assignments" ON public.assignments FOR SELECT USING (true);
CREATE POLICY "Public Read StatusHistory" ON public.incident_status_history FOR SELECT USING (true);
CREATE POLICY "Public Read Notifications" ON public.notifications FOR SELECT USING (true);
CREATE POLICY "Public Read Complaints" ON public.complaints FOR SELECT USING (true);
CREATE POLICY "Public Read ComplaintUpdates" ON public.complaint_updates FOR SELECT USING (true);
CREATE POLICY "Public Read TrafficEvents" ON public.traffic_events FOR SELECT USING (true);
CREATE POLICY "Public Read PedestrianEvents" ON public.pedestrian_events FOR SELECT USING (true);
CREATE POLICY "Public Read Logs" ON public.system_logs FOR SELECT USING (true);

CREATE POLICY "Edge Insert Detections" ON public.detections FOR INSERT WITH CHECK (true);
CREATE POLICY "Edge Insert Locations" ON public.bus_locations FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Insert Incidents" ON public.incidents FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Update Incidents" ON public.incidents FOR UPDATE USING (true);
CREATE POLICY "Public Insert Evidence" ON public.evidence FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Insert Complaints" ON public.complaints FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Insert Logs" ON public.system_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Insert Notifications" ON public.notifications FOR INSERT WITH CHECK (true);
CREATE POLICY "Public Update Assignments" ON public.assignments FOR UPDATE USING (true);

-- 24. SEED SAMPLE PRODUCTION DATA
INSERT INTO public.departments (dept_id, name, code, contact_email, contact_phone, jurisdiction_area)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Road Maintenance Department', 'DEPT-ROAD', 'roads@kmcgov.in', '+91 33 2286 1000', 'Road Maintenance & Pothole Squad'),
    ('a0000000-0000-0000-0000-000000000002', 'Drainage Department', 'DEPT-DRAIN', 'drainage@kmcgov.in', '+91 33 2286 2000', 'Stormwater & Waterlogging Drainage Control'),
    ('a0000000-0000-0000-0000-000000000003', 'Traffic Department', 'DEPT-TRAFFIC', 'traffic@kolkatapolice.gov.in', '+91 33 2214 3000', 'Traffic Management & Signal Control'),
    ('a0000000-0000-0000-0000-000000000004', 'Urban Infrastructure', 'DEPT-URBAN', 'infra@kmcgov.in', '+91 33 2214 4000', 'City Assets & Pedestrian Infrastructure')
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.buses (bus_code, registration_number, route_name, status, last_latitude, last_longitude, last_seen_at)
VALUES
    ('BUS-07', 'WB-04-E-2910', 'Park Street → Esplanade', 'ACTIVE', 22.5512, 88.3524, NOW()),
    ('BUS-12', 'WB-04-E-3122', 'AJC Bose Road → Sealdah', 'ACTIVE', 22.5415, 88.3578, NOW()),
    ('BUS-15', 'WB-04-E-4590', 'Esplanade → Howrah', 'ACTIVE', 22.5645, 88.3518, NOW()),
    ('BUS-21', 'WB-04-E-1882', 'Salt Lake → New Town', 'ACTIVE', 22.5760, 88.4320, NOW()),
    ('BUS-32', 'WB-04-E-9041', 'Garia → Tollygunge', 'IDLE', 22.4640, 88.3720, NOW())
ON CONFLICT (bus_code) DO NOTHING;

INSERT INTO public.cameras (camera_id, bus_id, model, mount_position, status)
VALUES
    ('CAM-BUS07-F', 'BUS-07', 'Sony IMX477 4K HDR', 'FRONT_WINDSHIELD', 'ONLINE'),
    ('CAM-BUS12-F', 'BUS-12', 'Sony IMX477 4K HDR', 'FRONT_WINDSHIELD', 'ONLINE'),
    ('CAM-BUS15-F', 'BUS-15', 'Sony IMX477 4K HDR', 'FRONT_WINDSHIELD', 'ONLINE'),
    ('CAM-BUS21-F', 'BUS-21', 'Sony IMX477 4K HDR', 'FRONT_WINDSHIELD', 'ONLINE')
ON CONFLICT (camera_id) DO NOTHING;

INSERT INTO public.camera_streams (camera_id, bus_id, stream_path, rtsp_url, webrtc_url, hls_url)
VALUES
    ('CAM-BUS07-F', 'BUS-07', 'bus07', 'rtsp://localhost:8554/bus07', 'http://localhost:8889/bus07/whep', 'http://localhost:8888/bus07/index.m3u8'),
    ('CAM-BUS12-F', 'BUS-12', 'bus12', 'rtsp://localhost:8554/bus12', 'http://localhost:8889/bus12/whep', 'http://localhost:8888/bus12/index.m3u8'),
    ('CAM-BUS15-F', 'BUS-15', 'bus15', 'rtsp://localhost:8554/bus15', 'http://localhost:8889/bus15/whep', 'http://localhost:8888/bus15/index.m3u8'),
    ('CAM-BUS21-F', 'BUS-21', 'bus21', 'rtsp://localhost:8554/bus21', 'http://localhost:8889/bus21/whep', 'http://localhost:8888/bus21/index.m3u8')
ON CONFLICT (stream_path) DO NOTHING;

INSERT INTO public.bus_locations (bus_id, latitude, longitude, speed_kmh, heading_deg)
VALUES
    ('BUS-07', 22.5512, 88.3524, 34.2, 85.0),
    ('BUS-12', 22.5415, 88.3578, 28.5, 120.0),
    ('BUS-15', 22.5645, 88.3518, 22.0, 310.0),
    ('BUS-21', 22.5760, 88.4320, 42.1, 45.0);

INSERT INTO public.incidents (incident_id, title, category, severity, severity_reason, status, duplicate_status, latitude, longitude, address, consensus_count, confidence_score, verified_by_buses)
VALUES
    ('RD-1042', 'Severe Lane Pothole near Park Hotel', 'Pothole', 'HIGH', 'Large defect depth (8.8cm) + Multi-Bus Consensus (3 buses) + High-density arterial route', 'VERIFIED', 'confirmed_duplicate', 22.5512, 88.3524, 'Park Street, Kolkata', 3, 98.4, ARRAY['BUS-07', 'BUS-12', 'BUS-15']),
    ('RD-1088', 'Heavy Waterlogging Descent', 'Waterlogging', 'HIGH', 'Moderate depth (6.2cm) + Dual-bus confirmed (2 buses) + Arterial transit corridor', 'POSSIBLE DUPLICATE', 'possible_duplicate', 22.5415, 88.3578, 'AJC Bose Road Crossing, Kolkata', 2, 96.1, ARRAY['BUS-12', 'BUS-07']),
    ('RD-1104', 'Critical Trench Subsidence near Metro Entrance', 'Road Damage', 'CRITICAL', 'Large defect geometry (Depth: 12.4cm, Area: 2200cm²) + Multi-Bus Consensus (4 buses) + High-density transit route', 'VERIFIED', 'confirmed_duplicate', 22.5645, 88.3518, 'Esplanade Central, Kolkata', 4, 99.2, ARRAY['BUS-15', 'BUS-07', 'BUS-12', 'BUS-21']),
    ('RD-0992', 'Surface Patch Applied & Cured', 'Pothole', 'MEDIUM', 'Standard Edge Detection Heuristics', 'RESOLVED', 'confirmed_duplicate', 22.5468, 88.3541, 'Camac Street, Kolkata', 3, 97.5, ARRAY['BUS-07', 'BUS-12'])
ON CONFLICT (incident_id) DO NOTHING;

INSERT INTO public.notifications (title, message, type, severity, link_url)
VALUES
    ('Critical Defect Detected on Esplanade', 'Major road subsidence trench (depth >12cm) detected by BUS-15.', 'INCIDENT_ALERT', 'CRITICAL', '#map-section'),
    ('Work Order Dispatched for Park Street', 'KMC Rapid Squad-01 dispatched to RD-1042.', 'WORK_ORDER', 'HIGH', '#maintenance-section');

INSERT INTO public.traffic_events (bus_id, location, latitude, longitude, congestion_level, congestion_score, avg_speed_kmh, cars_pct, buses_pct, motorcycles_pct, trucks_pct)
VALUES
    ('BUS-15', 'Esplanade Crossing, Kolkata', 22.5645, 88.3518, 'HIGH', 78, 18.4, 42, 21, 25, 12),
    ('BUS-07', 'Park Street, Kolkata', 22.5512, 88.3524, 'MODERATE', 45, 31.2, 38, 22, 28, 12);

-- 25. SUPABASE REALTIME REPLICATION (Real-time Broadcast on 6 Tables)
DO $$
BEGIN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.incidents;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.detections;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.bus_locations;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.notifications;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.complaints;
    ALTER PUBLICATION supabase_realtime ADD TABLE public.incident_status_history;
EXCEPTION
    WHEN OTHERS THEN
        NULL; -- Continue safely if already added
END $$;
