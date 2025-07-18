// Get a reference to the body element
const bodyElement = document.body;
// Get a reference to the theme toggle button
const toggleBtn = document.getElementById('dark-mode-toggle');

// --- Set initial theme on page load ---
// Check user's preference from localStorage
const userPref = localStorage.getItem('theme');

// If there's a stored preference, apply it
if (userPref === 'dark') {
  bodyElement.classList.add('dark');
} else if (userPref === 'light') {
  // Ensure 'dark' class is removed if 'light' was explicitly saved
  bodyElement.classList.remove('dark');
} else {
  // If no preference stored, check system preference (optional, but good practice)
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    bodyElement.classList.add('dark');
  }
}

// --- Update toggle button icon based on current theme ---
// This function can be called on page load and after a toggle
function updateToggleButtonIcon() {
  const isDark = bodyElement.classList.contains('dark');
  if (toggleBtn) { // Check if the button exists before trying to set its textContent
    toggleBtn.textContent = isDark ? '☀️' : '🌙';
    // Optional: Add an ARIA label for accessibility
    toggleBtn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
  }
}

// Call it once to set the initial icon
updateToggleButtonIcon();


// --- Add event listener for theme toggling ---
if (toggleBtn) { // Ensure the button exists before adding an event listener
  toggleBtn.addEventListener('click', () => {
    // Toggle the 'dark' class on the body
    bodyElement.classList.toggle('dark');

    // Check the new state of the theme
    const isDark = bodyElement.classList.contains('dark');

    // Save the preference to localStorage
    localStorage.setItem('theme', isDark ? 'dark' : 'light');

    // Update the button icon
    updateToggleButtonIcon();
  });
} else {
  console.warn("Theme toggle button with ID 'dark-mode-toggle' not found. Theme switching might not work.");
}