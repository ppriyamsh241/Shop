const menuBtn = document.querySelector('.menu-btn');
const nav = document.querySelector('.nav');
if (menuBtn) menuBtn.addEventListener('click', () => nav.classList.toggle('open'));
document.querySelectorAll('.nav a').forEach(link => link.addEventListener('click', () => nav.classList.remove('open')));
document.getElementById('year').textContent = new Date().getFullYear();

// Privacy-first visitor analytics. This GitHub Pages site cannot securely
// receive raw visitor IP addresses by itself. If you later add a backend,
// keep IP collection disabled or anonymized and publish a clear notice.
const CONSENT_KEY = 'pcc_analytics_consent';
const banner = document.getElementById('privacy-banner');
const analyticsAccept = document.getElementById('analytics-accept');
const locationAccept = document.getElementById('location-accept');
const analyticsDecline = document.getElementById('analytics-decline');

function setConsent(value) {
  localStorage.setItem(CONSENT_KEY, value);
  if (banner) banner.hidden = true;
}

function analyticsEvent() {
  if (localStorage.getItem(CONSENT_KEY) !== 'analytics') return;
  // Anonymous, local-only visit record: no IP, name, account or exact GPS.
  const visit = {
    time: new Date().toISOString(),
    page: location.pathname,
    language: navigator.language,
    device: /Mobi|Android|iPhone/i.test(navigator.userAgent) ? 'mobile' : 'desktop'
  };
  try { sessionStorage.setItem('pcc_visit', JSON.stringify(visit)); } catch (_) {}
}

if (localStorage.getItem(CONSENT_KEY)) banner.hidden = true;
if (analyticsAccept) analyticsAccept.addEventListener('click', () => { setConsent('analytics'); analyticsEvent(); });
if (analyticsDecline) analyticsDecline.addEventListener('click', () => setConsent('declined'));

// ---- Optional location / distance feature ----
const SHOP_LAT = 27.74; // Replace with exact store latitude
const SHOP_LNG = 84.18; // Replace with exact store longitude
const distanceText = document.getElementById('distance-text');
const distanceBtn = document.getElementById('distance-btn');

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = d => d * Math.PI / 180;
  const R = 6371;
  const dLat = toRad(lat2 - lat1), dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function showDistance(position) {
  const { latitude, longitude } = position.coords;
  const km = haversineKm(latitude, longitude, SHOP_LAT, SHOP_LNG);
  distanceText.textContent = `You're approximately ${km.toFixed(1)} km from Parajuli Cosmetic Centre.`;
  distanceBtn.textContent = 'Refresh';
}
function showLocationError(err) {
  distanceText.textContent = err.code === 1 ? 'Location access was declined.' : "Couldn't get your location. Please try again.";
  distanceBtn.textContent = 'Enable Location';
}
function requestLocation() {
  if (!navigator.geolocation) { distanceText.textContent = 'Location is not supported on this browser.'; return; }
  distanceText.textContent = 'Getting your location…';
  navigator.geolocation.getCurrentPosition(showDistance, showLocationError, { enableHighAccuracy: true, timeout: 10000 });
}

// Location is requested only after the visitor explicitly chooses it.
if (locationAccept) locationAccept.addEventListener('click', () => {
  setConsent('analytics');
  if (navigator.geolocation) requestLocation();
});
if (distanceBtn) distanceBtn.addEventListener('click', requestLocation);
