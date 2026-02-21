"use client";

import { useRef, useEffect } from "react";

// ── Particle types ──────────────────────────────────────────────────

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  opacity: number;
  parallaxFactor: number;
}

// ── Constants ───────────────────────────────────────────────────────

const PARTICLE_COUNT = 25;

const PARTICLE_COLORS = [
  "139, 92, 246",  // violet
  "236, 72, 153",  // rose
  "251, 146, 60",  // orange
];

// ── Helpers ─────────────────────────────────────────────────────────

function randomRange(min: number, max: number): number {
  return Math.random() * (max - min) + min;
}

function createParticle(width: number, height: number): Particle {
  return {
    x: Math.random() * width,
    y: Math.random() * height,
    vx: randomRange(-0.15, 0.15),
    vy: randomRange(-0.15, 0.15),
    radius: randomRange(1.5, 3.5),
    color: PARTICLE_COLORS[Math.floor(Math.random() * PARTICLE_COLORS.length)],
    opacity: randomRange(0.15, 0.35),
    parallaxFactor: randomRange(0.01, 0.04),
  };
}

// ── Component ───────────────────────────────────────────────────────

export function AmbientParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // ── Check reduced motion preference ──────────────────────────
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    // ── Resize handling with debounce ────────────────────────────
    let resizeTimer: ReturnType<typeof setTimeout>;
    let width = window.innerWidth;
    let height = window.innerHeight;

    function setCanvasSize() {
      const dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    setCanvasSize();

    function handleResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(setCanvasSize, 150);
    }

    window.addEventListener("resize", handleResize);

    // ── Initialize particles ─────────────────────────────────────
    const particles: Particle[] = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push(createParticle(width, height));
    }

    // ── Draw a single particle with radial glow ──────────────────
    function drawParticle(p: Particle, scrollY: number) {
      const drawX = p.x;
      const drawY = p.y + scrollY * p.parallaxFactor;

      // Wrap the parallax-adjusted y into viewport bounds for drawing
      const wrappedY = ((drawY % height) + height) % height;

      const glowRadius = p.radius * 3;
      const gradient = ctx!.createRadialGradient(
        drawX,
        wrappedY,
        0,
        drawX,
        wrappedY,
        glowRadius
      );
      gradient.addColorStop(0, `rgba(${p.color}, ${p.opacity})`);
      gradient.addColorStop(1, `rgba(${p.color}, 0)`);

      ctx!.beginPath();
      ctx!.arc(drawX, wrappedY, glowRadius, 0, Math.PI * 2);
      ctx!.fillStyle = gradient;
      ctx!.fill();
    }

    // ── Animation loop ───────────────────────────────────────────
    let animationId: number;

    function animate() {
      ctx!.clearRect(0, 0, width, height);
      const scrollY = window.scrollY;

      for (const p of particles) {
        // Move particle
        p.x += p.vx;
        p.y += p.vy;

        // Wrap around edges
        if (p.x > width) p.x = 0;
        if (p.x < 0) p.x = width;
        if (p.y > height) p.y = 0;
        if (p.y < 0) p.y = height;

        drawParticle(p, scrollY);
      }

      animationId = requestAnimationFrame(animate);
    }

    if (prefersReducedMotion) {
      // Render a single static frame
      ctx.clearRect(0, 0, width, height);
      const scrollY = window.scrollY;
      for (const p of particles) {
        drawParticle(p, scrollY);
      }
    } else {
      animationId = requestAnimationFrame(animate);
    }

    // ── Cleanup ──────────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(animationId);
      clearTimeout(resizeTimer);
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[1]"
    />
  );
}
