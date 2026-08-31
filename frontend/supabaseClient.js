/**
 * LUNARIS — Supabase Client Configuration & Realtime Sync
 * Production Schema for Project: ecmtwoccsdlhphdlutmz
 * SIH 2026 Problem SIH26124
 */

const SUPABASE_CONFIG = {
  url: 'https://ecmtwoccsdlhphdlutmz.supabase.co',
  anonKey: 'sb_publishable_l4l1lR2MLi_WOwtjs4CxTw_yBjCx01G',
  projectRef: 'ecmtwoccsdlhphdlutmz'
};

// Initialize Supabase JS Client
let supabaseClient = null;

if (window.supabase) {
  try {
    supabaseClient = window.supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.anonKey);
    console.log('[LUNARIS] Supabase Client Initialized:', SUPABASE_CONFIG.url);
  } catch (err) {
    console.error('[LUNARIS] Failed to initialize Supabase Client:', err);
  }
} else {
  console.warn('[LUNARIS] Supabase JS SDK not loaded yet.');
}

/**
 * Test Connection Heartbeat with Supabase
 */
async function testSupabaseConnection() {
  if (!supabaseClient) return { success: false, error: 'SDK not initialized' };

  try {
    const { data, error } = await supabaseClient
      .from('incidents')
      .select('count', { count: 'exact', head: true });

    if (error && error.code !== 'PGRST116') {
      return { success: true, tableReady: false, message: error.message };
    }
    return { success: true, tableReady: true, count: data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

/**
 * Fetch All Incidents from Supabase (Production public.incidents)
 */
async function fetchSupabaseIncidents() {
  if (!supabaseClient) return [];
  try {
    const { data, error } = await supabaseClient
      .from('incidents')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) {
      console.warn('[LUNARIS Supabase] fetchIncidents notice:', error.message);
      return [];
    }
    return data || [];
  } catch (e) {
    console.error('[LUNARIS Supabase] fetchIncidents error:', e);
    return [];
  }
}

/**
 * Fetch Bus Fleet from Supabase (public.buses)
 */
async function fetchSupabaseBusFleet() {
  if (!supabaseClient) return [];
  try {
    const { data, error } = await supabaseClient
      .from('buses')
      .select('*')
      .order('bus_code', { ascending: true });

    if (error) {
      console.warn('[LUNARIS Supabase] fetchBusFleet notice:', error.message);
      return [];
    }
    return data || [];
  } catch (e) {
    console.error('[LUNARIS Supabase] fetchBusFleet error:', e);
    return [];
  }
}

/**
 * Fetch Latest GPS Coordinates for Buses
 */
async function fetchSupabaseBusLocations() {
  if (!supabaseClient) return [];
  try {
    const { data, error } = await supabaseClient
      .from('bus_locations')
      .select('*')
      .order('recorded_at', { ascending: false })
      .limit(50);
    return data || [];
  } catch (e) {
    return [];
  }
}

/**
 * Fetch Notifications / Real-time Alerts from Supabase (public.notifications)
 */
async function fetchSupabaseAlerts() {
  if (!supabaseClient) return [];
  try {
    const { data, error } = await supabaseClient
      .from('notifications')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(15);

    if (error) {
      console.warn('[LUNARIS Supabase] fetchNotifications notice:', error.message);
      return [];
    }
    return data || [];
  } catch (e) {
    console.error('[LUNARIS Supabase] fetchNotifications error:', e);
    return [];
  }
}

/**
 * Fetch Traffic Events from Supabase (public.traffic_events)
 */
async function fetchSupabaseTrafficEvents() {
  if (!supabaseClient) return [];
  try {
    const { data, error } = await supabaseClient
      .from('traffic_events')
      .select('*')
      .order('recorded_at', { ascending: false })
      .limit(10);
    return data || [];
  } catch (e) {
    return [];
  }
}

/**
 * Insert a New Detected Incident into Supabase
 */
async function insertSupabaseIncident(incidentPayload) {
  if (!supabaseClient) throw new Error('Supabase client not ready');

  const { data, error } = await supabaseClient
    .from('incidents')
    .insert([incidentPayload])
    .select();

  if (error) throw error;
  return data;
}

/**
 * Supabase Auth API: Sign In with Email & Password
 */
async function supabaseSignIn(email, password) {
  if (!supabaseClient) throw new Error('Supabase client not ready');
  const { data, error } = await supabaseClient.auth.signInWithPassword({
    email,
    password
  });
  if (error) throw error;
  return data;
}

/**
 * Supabase Auth API: Sign Up with Email, Password, Full Name, & Role
 */
async function supabaseSignUp(email, password, fullName, role = 'viewer') {
  if (!supabaseClient) throw new Error('Supabase client not ready');
  const { data, error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: {
      data: {
        full_name: fullName,
        role: role
      }
    }
  });
  if (error) throw error;

  if (data?.user) {
    try {
      await supabaseClient.from('profiles').upsert([{
        user_id: data.user.id,
        email: email,
        full_name: fullName,
        role: role
      }], { onConflict: 'user_id' });
    } catch (e) {
      console.warn('[LUNARIS Auth] Profile insert note:', e);
    }
  }
  return data;
}

/**
 * Supabase Auth API: Sign Out
 */
async function supabaseSignOut() {
  if (!supabaseClient) return;
  const { error } = await supabaseClient.auth.signOut();
  if (error) console.error('[LUNARIS Auth] SignOut error:', error);
}

/**
 * Get Active Authenticated User Profile from public.profiles
 */
async function supabaseGetUserProfile() {
  if (!supabaseClient) return null;
  try {
    const { data: { user } } = await supabaseClient.auth.getUser();
    if (!user) return null;

    const { data, error } = await supabaseClient
      .from('profiles')
      .select('*')
      .eq('user_id', user.id)
      .maybeSingle();

    if (error || !data) {
      return {
        id: null,
        user_id: user.id,
        email: user.email,
        full_name: user.user_metadata?.full_name || user.email.split('@')[0],
        role: user.user_metadata?.role || 'viewer'
      };
    }
    return data;
  } catch (err) {
    console.error('[LUNARIS Auth] getUserProfile error:', err);
    return null;
  }
}

/**
 * Subscribe to Supabase Realtime WebSockets for Instant Dashboard Updates
 */
function subscribeSupabaseRealtime(onIncidentChange, onBusChange, onAlertChange) {
  if (!supabaseClient) return null;

  const channel = supabaseClient
    .channel('lunaris_production_hq')
    // Incidents Table Changes
    .on(
      'postgres_changes',
      { event: '*', schema: 'public', table: 'incidents' },
      (payload) => {
        console.log('[LUNARIS Realtime] Incidents update:', payload);
        if (typeof onIncidentChange === 'function') onIncidentChange(payload);
      }
    )
    // Buses & Locations
    .on(
      'postgres_changes',
      { event: '*', schema: 'public', table: 'bus_locations' },
      (payload) => {
        console.log('[LUNARIS Realtime] Bus Locations update:', payload);
        if (typeof onBusChange === 'function') onBusChange(payload);
      }
    )
    // Notifications / Alerts
    .on(
      'postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'notifications' },
      (payload) => {
        console.log('[LUNARIS Realtime] New Notification inserted:', payload);
        if (typeof onAlertChange === 'function') onAlertChange(payload);
      }
    )
    .subscribe((status) => {
      console.log('[LUNARIS Realtime] Channel status:', status);
      const statusEl = document.getElementById('supabase-realtime-status');
      if (statusEl) {
        if (status === 'SUBSCRIBED') {
          statusEl.innerText = 'REALTIME SYNCED 🟢';
          statusEl.className = 'text-emerald-400 font-bold';
        } else {
          statusEl.innerText = status;
        }
      }
    });

  return channel;
}
