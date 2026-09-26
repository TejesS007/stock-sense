// StockSense Main JS
document.addEventListener('DOMContentLoaded', () => {
    // Navigation active link detection
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href && (href === currentPath || (href !== '/' && href !== '/dashboard' && currentPath.startsWith(href)))) {
            link.classList.add('active');
        }
    });
});
