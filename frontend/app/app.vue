<template>
  <div class="min-h-screen bg-slate-50 dark:bg-dark-950 text-slate-800 dark:text-slate-100 font-sans transition-colors duration-300 relative">
    <!-- Animated mesh background -->
    <div class="fixed inset-0 z-0 overflow-hidden pointer-events-none transition-opacity duration-300">
      <div class="mesh-orb mesh-orb-1"></div>
      <div class="mesh-orb mesh-orb-2"></div>
      <div class="mesh-orb mesh-orb-3"></div>
      <div class="mesh-grid"></div>
    </div>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </div>
</template>

<script setup>
import { useTheme } from '~/composables/useTheme'
// Initialize theme
useTheme()
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap');

:root {
  /* LIGHT MODE */
  --bg-body: #f8fafc;
  --glass-bg: rgba(255, 255, 255, 0.7);
  --glass-border: rgba(255, 255, 255, 0.6);
  --glass-hover: rgba(255, 255, 255, 0.9);
  
  --glass-strong: rgba(255, 255, 255, 0.85);
  --glass-strong-border: rgba(255, 255, 255, 0.9);
  
  --glass-card-bg-1: rgba(255, 255, 255, 0.7);
  --glass-card-bg-2: rgba(255, 255, 255, 0.4);
  --glass-card-border: rgba(255, 255, 255, 0.8);
  --glass-card-hover-border: rgba(255, 255, 255, 1);
  --glass-card-shadow: 0 8px 32px rgba(148, 163, 184, 0.15);
  
  --glass-input-bg: rgba(255, 255, 255, 0.6);
  --glass-input-border: rgba(203, 213, 225, 0.6);
  --glass-input-text: #0f172a;
  --glass-input-placeholder: rgba(100, 116, 139, 0.7);
  --glass-input-focus: rgba(14, 165, 233, 0.4);
  
  --mesh-opacity: 0.6;
  --mesh-grid-color: rgba(15, 23, 42, 0.03);
  
  --glow-cyan: rgba(6, 182, 212, 0.4);
  --glow-violet: rgba(139, 92, 246, 0.4);
  --glow-brand: rgba(59, 130, 246, 0.4);
  
  --scrollbar-thumb: rgba(148, 163, 184, 0.4);
  --scrollbar-thumb-hover: rgba(148, 163, 184, 0.6);
}

html.dark {
  /* DARK MODE */
  --bg-body: #050a18;
  --glass-bg: rgba(255, 255, 255, 0.05);
  --glass-border: rgba(255, 255, 255, 0.08);
  --glass-hover: rgba(255, 255, 255, 0.1);
  
  --glass-strong: rgba(255, 255, 255, 0.08);
  --glass-strong-border: rgba(255, 255, 255, 0.12);
  
  --glass-card-bg-1: rgba(255, 255, 255, 0.06);
  --glass-card-bg-2: rgba(255, 255, 255, 0.02);
  --glass-card-border: rgba(255, 255, 255, 0.08);
  --glass-card-hover-border: rgba(255, 255, 255, 0.15);
  --glass-card-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  
  --glass-input-bg: rgba(255, 255, 255, 0.05);
  --glass-input-border: rgba(255, 255, 255, 0.1);
  --glass-input-text: #e2e8f0;
  --glass-input-placeholder: rgba(148, 163, 184, 0.5);
  --glass-input-focus: rgba(6, 182, 212, 0.5);
  
  --mesh-opacity: 0.4;
  --mesh-grid-color: rgba(255, 255, 255, 0.03);
  
  --scrollbar-thumb: rgba(255, 255, 255, 0.1);
  --scrollbar-thumb-hover: rgba(255, 255, 255, 0.2);
}

html {
  color-scheme: light;
}
html.dark {
  color-scheme: dark;
}

body {
  font-family: 'Inter', sans-serif;
  background: var(--bg-body);
  transition: background-color 0.3s ease;
}

/* Animated Mesh Background Orbs */
.mesh-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  opacity: var(--mesh-opacity);
  transition: opacity 0.3s ease;
}

.mesh-orb-1 {
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.3) 0%, transparent 70%);
  top: -10%;
  right: -5%;
  animation: mesh-float-1 20s ease-in-out infinite;
}

.mesh-orb-2 {
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.25) 0%, transparent 70%);
  bottom: -10%;
  left: -5%;
  animation: mesh-float-2 25s ease-in-out infinite;
}

.mesh-orb-3 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.2) 0%, transparent 70%);
  top: 40%;
  left: 30%;
  animation: mesh-float-3 18s ease-in-out infinite;
}

/* Subtle dot grid overlay */
.mesh-grid {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(var(--mesh-grid-color) 1px, transparent 1px);
  background-size: 40px 40px;
  transition: background-image 0.3s ease;
}

@keyframes mesh-float-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-50px, 30px) scale(1.1); }
  66% { transform: translate(30px, -40px) scale(0.9); }
}

@keyframes mesh-float-2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(40px, -30px) scale(1.15); }
  66% { transform: translate(-30px, 50px) scale(0.95); }
}

@keyframes mesh-float-3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, 40px) scale(1.05); }
  66% { transform: translate(-40px, -20px) scale(0.95); }
}

/* Glass utility classes */
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-border);
  transition: background 0.3s ease, border-color 0.3s ease;
}

.glass-strong {
  background: var(--glass-strong);
  backdrop-filter: blur(30px);
  -webkit-backdrop-filter: blur(30px);
  border: 1px solid var(--glass-strong-border);
  transition: background 0.3s ease, border-color 0.3s ease;
}

.glass-card {
  background: linear-gradient(135deg, var(--glass-card-bg-1) 0%, var(--glass-card-bg-2) 100%);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--glass-card-border);
  transition: all 0.3s ease;
}

.glass-card:hover {
  border-color: var(--glass-card-hover-border);
  box-shadow: var(--glass-card-shadow);
}

.glass-input {
  background: var(--glass-input-bg);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--glass-input-border);
  color: var(--glass-input-text);
  transition: all 0.3s ease;
}

.glass-input:focus {
  border-color: var(--glass-input-focus);
  box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.1);
  outline: none;
}

.glass-input::placeholder {
  color: var(--glass-input-placeholder);
}

/* Gradient text utility */
.text-gradient {
  background: linear-gradient(135deg, #0ea5e9, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
html.dark .text-gradient {
  background: linear-gradient(135deg, #06b6d4, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.text-gradient-brand {
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
html.dark .text-gradient-brand {
  background: linear-gradient(135deg, #60a5fa, #06b6d4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* Glow button */
.btn-glow {
  background: linear-gradient(135deg, #0ea5e9, #3b82f6);
  position: relative;
  overflow: hidden;
  transition: all 0.3s ease;
}
html.dark .btn-glow {
  background: linear-gradient(135deg, #06b6d4, #3b82f6);
}

.btn-glow:hover {
  box-shadow: 0 0 30px rgba(14, 165, 233, 0.4), 0 0 60px rgba(59, 130, 246, 0.2);
  transform: translateY(-1px);
}
html.dark .btn-glow:hover {
  box-shadow: 0 0 30px rgba(6, 182, 212, 0.4), 0 0 60px rgba(59, 130, 246, 0.2);
}

.btn-glow::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent, rgba(255,255,255,0.2), transparent);
  transform: translateX(-100%);
  transition: transform 0.5s ease;
}

.btn-glow:hover::after {
  transform: translateX(100%);
}

/* Custom Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 3px;
  transition: background 0.3s ease;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}

/* Neon indicator */
.neon-dot {
  box-shadow: 0 0 6px currentColor, 0 0 12px currentColor;
}

/* Animated border gradient */
.border-gradient {
  position: relative;
}

.border-gradient::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.4), rgba(139, 92, 246, 0.4), rgba(14, 165, 233, 0.4));
  background-size: 200% 200%;
  animation: gradient-shift 4s ease infinite;
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
html.dark .border-gradient::before {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.3), rgba(139, 92, 246, 0.3), rgba(6, 182, 212, 0.3));
}

@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
</style>
