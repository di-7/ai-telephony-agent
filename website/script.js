/* ==========================================
   MIXUP — Interactive Scripts
   ========================================== */

document.addEventListener('DOMContentLoaded', () => {

    // --- Create Animated Particles ---
    createParticles();

    // --- Scroll Progress Indicator ---
    initScrollProgress();

    // --- Floating CTA ---
    initFloatingCta();

    // --- Scroll Reveal Animation ---
    const revealElements = document.querySelectorAll('.reveal');

    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry, index) => {
            if (entry.isIntersecting) {
                // Stagger the reveal animation
                setTimeout(() => {
                    entry.target.classList.add('visible');
                }, index * 80);
                revealObserver.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -60px 0px'
    });

    revealElements.forEach(el => revealObserver.observe(el));


    // --- Navbar Scroll Effect ---
    const navbar = document.getElementById('navbar');
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;
        if (currentScroll > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
        lastScroll = currentScroll;
    }, { passive: true });


    // --- Mobile Nav Toggle ---
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    navToggle.addEventListener('click', () => {
        navToggle.classList.toggle('active');
        navLinks.classList.toggle('active');
        document.body.style.overflow = navLinks.classList.contains('active') ? 'hidden' : '';
    });

    // Close mobile nav on link click
    navLinks.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            navToggle.classList.remove('active');
            navLinks.classList.remove('active');
            document.body.style.overflow = '';
        });
    });


    // --- Stat Counter Animation ---
    const statNumbers = document.querySelectorAll('.stat-number[data-target]');

    const counterObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                counterObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });

    statNumbers.forEach(el => counterObserver.observe(el));

    function animateCounter(element) {
        const target = parseInt(element.getAttribute('data-target'));
        const duration = 2000;
        const startTime = performance.now();

        function updateCounter(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease-out cubic
            const easedProgress = 1 - Math.pow(1 - progress, 3);
            const current = Math.floor(easedProgress * target);

            element.textContent = current;

            if (progress < 1) {
                requestAnimationFrame(updateCounter);
            } else {
                element.textContent = target;
            }
        }

        requestAnimationFrame(updateCounter);
    }


    // --- Smooth Scroll for Anchor Links ---
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const targetEl = document.querySelector(targetId);
            if (targetEl) {
                const navHeight = navbar.offsetHeight;
                const targetPosition = targetEl.getBoundingClientRect().top + window.pageYOffset - navHeight - 20;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });


    // --- Contact Form Handler ---
    const contactForm = document.getElementById('contactForm');
    const submitBtn = document.getElementById('submitBtn');

    if (contactForm) {
        contactForm.addEventListener('submit', (e) => {
            e.preventDefault();

            const name = document.getElementById('nameInput').value;
            const rawPhone = document.getElementById('phoneInput').value.trim();
            const countryCode = document.getElementById('ctaCountryCode').value;
            const email = document.getElementById('emailInput').value;
            const company = document.getElementById('companyInput').value;
            
            // Combine country code + phone number
            const phone = countryCode + rawPhone.replace(/^\+/, '').replace(/^0+/, '');

            // Show success state and simulate ring
            submitBtn.innerHTML = `
                <span style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 18px; height: 18px;">
                        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                    </svg>
                    Calling you now...
                </span>
            `;
            submitBtn.style.background = 'linear-gradient(135deg, #22c55e, #14b8a6)';
            submitBtn.style.boxShadow = '0 4px 20px rgba(34, 197, 94, 0.3)';
            submitBtn.disabled = true;

            // Trigger actual call
            fetch('https://ai-telephony-agent.onrender.com/api/make-call', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    to_number: phone, 
                    name: name,
                    email: email,
                    company: company
                })
            }).catch(err => console.error("CTA call trigger failed:", err));

            // Reset after 10 seconds
            setTimeout(() => {
                submitBtn.innerHTML = `
                    <span>Book Your Demo</span>
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M4 10h12m-4-4l4 4-4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                `;
                submitBtn.style.background = '';
                submitBtn.style.boxShadow = '';
                submitBtn.disabled = false;
                contactForm.reset();
            }, 10000);
        });
    }


    // --- Parallax on Ambient Orbs ---
    let mouseX = 0, mouseY = 0;
    let orbX = 0, orbY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
        mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    });

    function updateParallax() {
        orbX += (mouseX - orbX) * 0.02;
        orbY += (mouseY - orbY) * 0.02;

        const orbs = document.querySelectorAll('.orb');
        orbs.forEach((orb, i) => {
            const factor = (i + 1) * 15;
            orb.style.transform = `translate(${orbX * factor}px, ${orbY * factor}px)`;
        });

        requestAnimationFrame(updateParallax);
    }

    // Only enable parallax on desktop
    if (window.innerWidth > 768) {
        updateParallax();
    }


    // --- Active Nav Link Highlight ---
    const sections = document.querySelectorAll('section[id]');

    window.addEventListener('scroll', () => {
        const scrollY = window.pageYOffset;
        const navHeight = navbar.offsetHeight;

        sections.forEach(section => {
            const sectionTop = section.offsetTop - navHeight - 100;
            const sectionBottom = sectionTop + section.offsetHeight;
            const sectionId = section.getAttribute('id');

            if (scrollY >= sectionTop && scrollY < sectionBottom) {
                document.querySelectorAll('.nav-link').forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${sectionId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, { passive: true });

});

// --- Instant Call Modal Logic ---
function openInstantCallModal() {
    const modal = document.getElementById('instantCallModal');
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeInstantCallModal() {
    const modal = document.getElementById('instantCallModal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';

        // Reset status
        const callStatus = document.getElementById('callStatus');
        const callMeBtn = document.getElementById('callMeBtn');
        const phoneInput = document.getElementById('modalPhoneInput');

        if (callStatus) callStatus.style.display = 'none';
        if (callMeBtn) callMeBtn.style.display = 'flex';
        if (phoneInput) phoneInput.value = '';
    }
}

// Close modal when clicking outside
document.addEventListener('click', (e) => {
    const modal = document.getElementById('instantCallModal');
    if (modal && modal.classList.contains('active') && e.target === modal) {
        closeInstantCallModal();
    }
});

function initiateCall() {
    const rawPhone = document.getElementById('modalPhoneInput').value.trim();
    const countryCode = document.getElementById('modalCountryCode').value;
    
    if (!rawPhone || rawPhone.length < 5) {
        alert("Please enter a valid phone number.");
        return;
    }
    
    // Combine country code + phone number (strip leading + or 0 from raw input)
    const phoneInput = countryCode + rawPhone.replace(/^\+/, '').replace(/^0+/, '');

    const callStatus = document.getElementById('callStatus');
    const callMeBtn = document.getElementById('callMeBtn');

    // UI Feedback
    callMeBtn.style.display = 'none';
    callStatus.style.display = 'flex';

    // INTERGRATION POINT - Call the backend endpoint
    fetch('https://ai-telephony-agent.onrender.com/api/make-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_number: phoneInput })
    }).catch(err => console.error("Call trigger failed:", err));

    // Simulate backend processing and active call state
    setTimeout(() => {
        callStatus.innerHTML = `
            <div style="margin-bottom: 12px; color: var(--color-signal-coral);">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 48px; height: 48px; animation: pulse-float 1.5s ease-in-out infinite;">
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
            </div>
            <span style="color: var(--text-primary); font-size: 1.1rem;">Your phone is ringing!</span>
            <span style="color: var(--text-secondary); margin-top: -8px;">Answer it to speak with the AI.</span>
        `;
        callStatus.style.background = 'transparent';
        callStatus.style.border = 'none';

        // Automatically close after some time
        setTimeout(() => {
            closeInstantCallModal();
        }, 12000);
    }, 2000);
}

// --- Create Animated Particles ---
function createParticles() {
    const container = document.getElementById('particlesContainer');
    if (!container) return;

    const particleCount = 30;
    
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Random position
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        
        // Random animation delay and duration
        particle.style.animationDelay = Math.random() * 20 + 's';
        particle.style.animationDuration = (15 + Math.random() * 15) + 's';
        
        // Random size
        const size = 2 + Math.random() * 4;
        particle.style.width = size + 'px';
        particle.style.height = size + 'px';
        
        container.appendChild(particle);
    }
}

// --- Scroll Progress Indicator ---
function initScrollProgress() {
    const progressBar = document.getElementById('scrollProgress');
    if (!progressBar) return;

    window.addEventListener('scroll', () => {
        const windowHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrolled = (window.scrollY / windowHeight) * 100;
        progressBar.style.width = scrolled + '%';
    }, { passive: true });
}

// --- Floating CTA ---
function initFloatingCta() {
    const floatingCta = document.getElementById('floatingCta');
    if (!floatingCta) return;

    // Floating call button is permanently active at bottom-right corner
    floatingCta.classList.add('visible');
}

// --- Smooth Scroll with Easing ---
function smoothScrollTo(targetY, duration = 800) {
    const startY = window.pageYOffset;
    const distance = targetY - startY;
    const startTime = performance.now();
    
    function easeInOutCubic(t) {
        return t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
    }
    
    function step(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easedProgress = easeInOutCubic(progress);
        
        window.scrollTo(0, startY + distance * easedProgress);
        
        if (progress < 1) {
            requestAnimationFrame(step);
        }
    }
    
    requestAnimationFrame(step);
}

// --- Add Morphing Shapes to Hero ---
function addMorphingShapes() {
    const hero = document.querySelector('.hero');
    if (!hero) return;

    const shapes = [
        { width: '400px', height: '400px', background: 'var(--color-signal-coral)', top: '10%', left: '5%' },
        { width: '300px', height: '300px', background: 'var(--color-ember-wash)', top: '60%', right: '10%' },
        { width: '250px', height: '250px', background: 'var(--color-persimmon)', bottom: '20%', left: '60%' }
    ];

    shapes.forEach((shapeConfig, index) => {
        const shape = document.createElement('div');
        shape.className = 'morph-shape';
        Object.assign(shape.style, shapeConfig);
        shape.style.animationDelay = (index * 3) + 's';
        hero.appendChild(shape);
    });
}

// Initialize morphing shapes
addMorphingShapes();

