const menuBtn = document.querySelector('.menu-btn');
const nav = document.querySelector('.nav');

menuBtn.addEventListener('click', () => {
  nav.classList.toggle('open');
});

document.querySelectorAll('.nav a').forEach(link => {
  link.addEventListener('click', () => nav.classList.remove('open'));
});

document.getElementById('year').textContent = new Date().getFullYear();

// ---- "Distance from store" feature ----
// This runs entirely in the visitor's own browser. It asks the browser for
// permission to read the visitor's location, then shows THAT SAME VISITOR
// how far they are from the store. Nothing is sent to a server, logged, or
// stored anywhere — the coordinates never leave the page.
//
// IMPORTANT: set these to your store's real coordinates before publishing.
// Easiest way: open Google Maps, right-click your store's exact spot, and
// click the "lat, lng" numbers at the top of the menu to copy them.
const SHOP_LAT = 27.74;  // TODO: replace with your store's exact latitude
const SHOP_LNG = 84.18;  // TODO: replace with your store's exact longitude

const distanceText = document.getElementById('distance-text');
const distanceBtn = document.getElementById('distance-btn');

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = deg => (deg * Math.PI) / 180;
  const R = 6371; // Earth's radius in km
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function showDistance(position) {
  const { latitude, longitude } = position.coords;
  const km = haversineKm(latitude, longitude, SHOP_LAT, SHOP_LNG);
  distanceText.textContent = `You're approximately ${km.toFixed(1)} km from Parajuli Cosmetic Centre.`;
  distanceBtn.textContent = 'Refresh';
}

function showLocationError(err) {
  distanceText.textContent =
    err.code === err.PERMISSION_DENIED
      ? "Location access was declined. Tap 'Enable Location' any time to try again."
      : "Couldn't get your location just now. Please try again.";
  distanceBtn.textContent = 'Enable Location';
}

function requestLocation() {
  if (!navigator.geolocation) {
    distanceText.textContent = 'Location is not supported on this browser.';
    return;
  }
  distanceText.textContent = 'Getting your location…';
  navigator.geolocation.getCurrentPosition(showDistance, showLocationError, {
    enableHighAccuracy: true,
    timeout: 10000,
  });
}

if (distanceBtn) {
  // Ask automatically when the page loads (matches the browser's native
  // permission prompt), and let the visitor retry manually via the button.
  requestLocation();
  distanceBtn.addEventListener('click', requestLocation);
}
