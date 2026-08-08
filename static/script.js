const header = document.querySelector(".site-header");
const menuToggle = document.querySelector(".menu-toggle");
const navLinks = document.querySelector(".nav-links");
const revealItems = document.querySelectorAll(".reveal, .reveal-left, .reveal-right, .reveal-scale");
const contactForm = document.querySelector(".contact-form");
const formNote = document.querySelector(".form-note");
const popup = document.querySelector("[data-popup]");
const heroVisual = document.querySelector(".hero-visual");
const heroCarousel = document.querySelector("[data-hero-carousel]");
const statValues = document.querySelectorAll(".stats strong");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (heroCarousel) {
  const slides = [...heroCarousel.querySelectorAll(".hero-carousel-slide")];
  const dots = [...heroCarousel.querySelectorAll("[data-carousel-dot]")];
  const prevBtn = heroCarousel.querySelector("[data-carousel-prev]");
  const nextBtn = heroCarousel.querySelector("[data-carousel-next]");
  let activeIndex = 0;
  let timerId = null;

  const showSlide = (index) => {
    activeIndex = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === activeIndex);
    });
    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle("is-active", dotIndex === activeIndex);
    });
  };

  const stopAutoplay = () => {
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  };

  const startAutoplay = () => {
    if (reducedMotion || slides.length < 2) {
      return;
    }
    stopAutoplay();
    timerId = setInterval(() => showSlide(activeIndex + 1), 4500);
  };

  prevBtn?.addEventListener("click", () => {
    showSlide(activeIndex - 1);
    startAutoplay();
  });
  nextBtn?.addEventListener("click", () => {
    showSlide(activeIndex + 1);
    startAutoplay();
  });
  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      showSlide(Number(dot.dataset.carouselDot) || 0);
      startAutoplay();
    });
  });

  heroCarousel.addEventListener("mouseenter", stopAutoplay);
  heroCarousel.addEventListener("mouseleave", startAutoplay);
  startAutoplay();
}

const updateHeader = () => {
  if (header) {
    header.classList.toggle("scrolled", window.scrollY > 12);
  }
};

const updateParallax = () => {
  if (heroVisual && !reducedMotion) {
    heroVisual.style.transform = `translateY(${Math.min(window.scrollY * 0.12, 90)}px)`;
  }
};

const closeMenu = () => {
  if (!navLinks || !menuToggle) {
    return;
  }
  document.body.classList.remove("menu-open");
  navLinks.classList.remove("open");
  menuToggle.setAttribute("aria-expanded", "false");
};

if (menuToggle && navLinks) {
  menuToggle.addEventListener("click", () => {
    const isOpen = navLinks.classList.toggle("open");
    document.body.classList.toggle("menu-open", isOpen);
    menuToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navLinks.addEventListener("click", (event) => {
    if (event.target.matches("a")) {
      closeMenu();
    }
  });
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.18,
  }
);

revealItems.forEach((item, index) => {
  item.style.transitionDelay = `${Math.min(index * 70, 420)}ms`;
  revealObserver.observe(item);
});

const animateCounter = (element) => {
  const match = element.textContent.trim().match(/^(\d+)(.*)$/);
  if (!match) {
    return;
  }
  const target = Number(match[1]);
  const suffix = match[2];
  const duration = 1200;
  const start = performance.now();

  const tick = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = `${Math.round(target * eased)}${suffix}`;
    if (progress < 1) {
      requestAnimationFrame(tick);
    }
  };

  requestAnimationFrame(tick);
};

if (statValues.length && !reducedMotion) {
  const statsObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          statsObserver.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.6,
    }
  );

  statValues.forEach((value) => statsObserver.observe(value));
}

const photoInput = document.querySelector("[data-photo-input]");
const photoStatus = document.querySelector("[data-photo-status]");

const updatePhotoStatus = () => {
  if (!photoInput || !photoStatus) {
    return;
  }
  const count = photoInput.files?.length || 0;
  photoStatus.textContent = count
    ? `Vybrané fotky: ${count}`
    : "";
};

photoInput?.addEventListener("change", updatePhotoStatus);

// Ve statickém exportu (data-static) se formulář odesílá nativně přes mailto.
if (contactForm && formNote && !contactForm.hasAttribute("data-static")) {
  contactForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    formNote.textContent = "Odesíláme poptávku...";

    try {
      const response = await fetch(contactForm.action, {
        method: "POST",
        body: new FormData(contactForm),
        headers: {
          "X-Requested-With": "fetch",
        },
      });

      if (!response.ok) {
        throw new Error("Request failed");
      }

      const data = await response.json();
      formNote.textContent = data.message;
      contactForm.reset();
      updatePhotoStatus();
    } catch {
      formNote.textContent = "Poptávku se nepodařilo odeslat. Zkuste to prosím znovu.";
    }
  });
}

if (popup) {
  const close = popup.querySelector(".popup-close");
  close?.addEventListener("click", () => {
    popup.remove();
  });
}

let scrollScheduled = false;
window.addEventListener(
  "scroll",
  () => {
    if (scrollScheduled) {
      return;
    }
    scrollScheduled = true;
    requestAnimationFrame(() => {
      updateHeader();
      updateParallax();
      scrollScheduled = false;
    });
  },
  { passive: true }
);

window.addEventListener("resize", () => {
  if (window.innerWidth > 680) {
    closeMenu();
  }
});

updateHeader();
updateParallax();
