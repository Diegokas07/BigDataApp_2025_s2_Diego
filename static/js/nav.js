const toggle = document.querySelector('.nav-toggle');
const nav = document.querySelector('.nav');
if (toggle && nav) {
  toggle.addEventListener('click', () => {
    const open = getComputedStyle(nav).display !== 'none';
    nav.style.display = open ? 'none' : 'flex';
  });
}
