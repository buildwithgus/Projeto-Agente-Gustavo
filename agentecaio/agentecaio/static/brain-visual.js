(function () {
  const container = document.getElementById('brain-viewport');
  if (!container) {
    return;
  }

  const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (!window.THREE) {
    container.classList.add('brain-fallback');
    container.innerHTML = '<div class="brain-fallback-mark">CAIO</div>';
    return;
  }

  class HolographicCore {
    constructor(host) {
      this.host = host;
      this.state = 'idle';
      this.stateIntensity = {
        idle: 0.38,
        listening: 0.52,
        processing: 0.82,
        retrieving: 0.76,
        responding: 0.86,
        error: 0.68,
      };
      this.renderer = null;
      this.scene = null;
      this.camera = null;
      this.root = null;
      this.core = null;
      this.orbitGroup = null;
      this.lines = [];
      this.particles = null;
      this.pulseRings = [];
      this.halo = null;
      this.hudLines = [];
      this.rafId = null;
      this.animationStarted = false;
      this.resizeHandler = this.handleResize.bind(this);
    }

    init() {
      try {
        this.scene = new THREE.Scene();
        this.scene.fog = new THREE.Fog(0x020c1a, 8, 18);

        this.camera = new THREE.PerspectiveCamera(34, this.host.clientWidth / this.host.clientHeight, 0.1, 100);
        this.camera.position.set(0, 0.2, 6.2);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        this.renderer.setClearColor(0x000000, 0);
        this.host.appendChild(this.renderer.domElement);

        this.root = new THREE.Group();
        this.scene.add(this.root);

        const ambient = new THREE.AmbientLight(0x8bcffb, 0.9);
        this.scene.add(ambient);

        const glow = new THREE.PointLight(0x67d8ff, 2.8, 28, 2);
        glow.position.set(0, 1.8, 4.6);
        this.scene.add(glow);

        const rim = new THREE.PointLight(0x4379ff, 1.8, 20, 2);
        rim.position.set(-4.8, -2.6, -3.8);
        this.scene.add(rim);

        const fill = new THREE.PointLight(0xc7f3ff, 1.3, 14, 2);
        fill.position.set(4.5, 2.2, 1.8);
        this.scene.add(fill);

        this.core = this.createCore();
        this.root.add(this.core);

        this.halo = new THREE.Mesh(
          new THREE.SphereGeometry(2.5, 32, 32),
          new THREE.MeshBasicMaterial({
            color: 0x8be4ff,
            transparent: true,
            opacity: 0.08,
            side: THREE.BackSide,
          })
        );
        this.root.add(this.halo);

        this.orbitGroup = this.createOrbitGroup();
        this.root.add(this.orbitGroup);

        this.particles = this.createParticles();
        this.root.add(this.particles);

        this.pulseRings = this.createPulseRings();
        this.pulseRings.forEach((ring) => this.root.add(ring));

        this.hudLines = this.createHudLines();
        this.hudLines.forEach((line) => this.root.add(line));

        window.addEventListener('resize', this.resizeHandler);
        this.handleResize();
        this.startAnimation();
      } catch (error) {
        console.warn('Falha ao inicializar o núcleo holográfico:', error);
        this.host.classList.add('brain-fallback');
        this.host.innerHTML = '<div class="brain-fallback-mark">CAIO</div>';
      }
    }

    createCore() {
      const group = new THREE.Group();

      const outer = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.7, 2),
        new THREE.MeshPhysicalMaterial({
          color: 0x72d8ff,
          emissive: 0x123d80,
          emissiveIntensity: 0.9,
          transparent: true,
          opacity: 0.7,
          roughness: 0.24,
          metalness: 0.18,
          clearcoat: 1,
          clearcoatRoughness: 0.25,
        })
      );
      outer.scale.set(1.28, 1.08, 1.18);
      group.add(outer);

      const inner = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.03, 1),
        new THREE.MeshPhysicalMaterial({
          color: 0x9fe8ff,
          emissive: 0x0d5d9e,
          emissiveIntensity: 1.3,
          transparent: true,
          opacity: 0.9,
          roughness: 0.18,
          metalness: 0.25,
          clearcoat: 1,
          clearcoatRoughness: 0.2,
        })
      );
      group.add(inner);

      const wireMaterial = new THREE.MeshBasicMaterial({ color: 0x7fe7ff, transparent: true, opacity: 0.42 });
      const curves = [
        [
          new THREE.Vector3(-1.8, 0.6, 0.3),
          new THREE.Vector3(-0.8, 1.5, 0.8),
          new THREE.Vector3(0.2, 1.2, 0.3),
          new THREE.Vector3(1.6, 0.8, 0.4),
          new THREE.Vector3(1.8, -0.4, 0.1),
        ],
        [
          new THREE.Vector3(-1.7, -0.5, -0.2),
          new THREE.Vector3(-0.5, -1.5, 0.5),
          new THREE.Vector3(0.6, -1.1, 0.7),
          new THREE.Vector3(1.4, -0.7, -0.1),
          new THREE.Vector3(1.8, 0.4, -0.6),
        ],
        [
          new THREE.Vector3(-1.1, 1.8, -0.6),
          new THREE.Vector3(-0.2, 0.9, 0.9),
          new THREE.Vector3(0.7, 1.4, 0.2),
          new THREE.Vector3(1.4, 0.2, -0.5),
          new THREE.Vector3(1.2, -1.5, -0.6),
        ],
      ];

      curves.forEach((points, index) => {
        const curve = new THREE.CatmullRomCurve3(points);
        const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.025 + index * 0.006, 10, false), wireMaterial.clone());
        tube.rotation.z = index * 0.8;
        group.add(tube);
      });

      const radial = new THREE.Mesh(
        new THREE.TorusGeometry(1.55, 0.02, 12, 120),
        new THREE.MeshBasicMaterial({ color: 0x7ad8ff, transparent: true, opacity: 0.7 })
      );
      radial.rotation.x = Math.PI / 2.8;
      group.add(radial);

      const radial2 = radial.clone();
      radial2.rotation.y = Math.PI / 2.3;
      radial2.rotation.x = Math.PI / 1.8;
      group.add(radial2);

      const halo = new THREE.Mesh(
        new THREE.TorusGeometry(2.1, 0.06, 16, 180),
        new THREE.MeshBasicMaterial({ color: 0x8ee7ff, transparent: true, opacity: 0.48 })
      );
      halo.rotation.x = Math.PI / 2.2;
      halo.rotation.y = 0.5;
      group.add(halo);

      const scanRing = new THREE.Mesh(
        new THREE.TorusGeometry(2.45, 0.012, 8, 160),
        new THREE.MeshBasicMaterial({ color: 0x63e6ff, transparent: true, opacity: 0.26 })
      );
      scanRing.rotation.x = Math.PI / 1.8;
      scanRing.rotation.y = Math.PI / 3;
      group.add(scanRing);

      const nodes = new THREE.Group();
      for (let i = 0; i < 9; i += 1) {
        const node = new THREE.Mesh(
          new THREE.SphereGeometry(0.09, 16, 16),
          new THREE.MeshBasicMaterial({ color: 0xbff7ff, transparent: true, opacity: 0.9 })
        );
        const angle = (i / 9) * Math.PI * 2;
        node.position.set(Math.cos(angle) * 1.75, Math.sin(angle * 2.3) * 0.8, Math.sin(angle) * 1.6);
        nodes.add(node);
      }
      group.add(nodes);

      group.rotation.x = 0.4;
      group.rotation.z = -0.2;
      return group;
    }

    createOrbitGroup() {
      const group = new THREE.Group();
      const colorSet = [0x7de8ff, 0x4d9dff, 0x8ec1ff, 0x9af6ff];

      for (let i = 0; i < 5; i += 1) {
        const radius = 2.2 + i * 0.38;
        const geometry = new THREE.TorusGeometry(radius, 0.018, 12, 150, Math.PI * 2);
        const material = new THREE.MeshBasicMaterial({
          color: colorSet[i % colorSet.length],
          transparent: true,
          opacity: 0.28 + i * 0.07,
        });
        const ring = new THREE.Mesh(geometry, material);
        ring.rotation.x = Math.PI / (2.2 + i * 0.35);
        ring.rotation.y = i * 0.7;
        group.add(ring);
        this.lines.push(ring);
      }

      for (let i = 0; i < 14; i += 1) {
        const curve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(Math.cos(i * 0.5) * 1.8, Math.sin(i * 0.9) * 0.8, Math.sin(i * 0.7) * 1.5),
          new THREE.Vector3(Math.cos(i * 0.9 + 1.2) * 2.1, Math.sin(i * 1.3) * 1.2, Math.cos(i * 0.9) * 1.6),
          new THREE.Vector3(Math.sin(i * 0.8) * 1.9, Math.cos(i * 1.4) * 1.4, Math.sin(i * 1.1 + 1.5) * 2.1),
        ]);
        const tube = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 60, 0.011, 6, false),
          new THREE.MeshBasicMaterial({ color: 0x8ae9ff, transparent: true, opacity: 0.2 })
        );
        group.add(tube);
        this.lines.push(tube);
      }

      return group;
    }

    createParticles() {
      const positions = [];
      const colors = [];
      for (let i = 0; i < 220; i += 1) {
        const angle = Math.random() * Math.PI * 2;
        const elevation = (Math.random() - 0.5) * Math.PI;
        const radius = 1.05 + Math.random() * 1.7;
        const x = Math.sin(elevation) * Math.cos(angle) * radius;
        const y = Math.cos(elevation) * radius * 0.8;
        const z = Math.sin(elevation) * Math.sin(angle) * radius;
        positions.push(x, y, z);
        const c = new THREE.Color().setHSL(0.52 + Math.random() * 0.12, 0.9, 0.72);
        colors.push(c.r, c.g, c.b);
      }

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

      const material = new THREE.PointsMaterial({
        size: 0.05,
        vertexColors: true,
        transparent: true,
        opacity: 0.86,
        depthWrite: false,
      });

      const particles = new THREE.Points(geometry, material);
      particles.rotation.x = 0.8;
      return particles;
    }

    createPulseRings() {
      const rings = [];
      for (let i = 0; i < 4; i += 1) {
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(1.1 + i * 0.42, 0.013, 8, 100),
          new THREE.MeshBasicMaterial({
            color: i % 2 === 0 ? 0x7fe7ff : 0x5da9ff,
            transparent: true,
            opacity: 0.12,
          })
        );
        ring.rotation.x = Math.PI / 2.3;
        ring.rotation.y = i * 0.8;
        rings.push(ring);
      }
      return rings;
    }

    createHudLines() {
      const lines = [];
      const colors = [0x7fe7ff, 0x77b6ff, 0x9ae7ff];
      for (let i = 0; i < 7; i += 1) {
        const points = [
          new THREE.Vector3(-2.8 + i * 0.7, -1.7 + (i % 2) * 0.8, -1.2 + (i % 3) * 0.5),
          new THREE.Vector3(0.8 + i * 0.35, 1.2 - i * 0.18, 1.4 - i * 0.15),
          new THREE.Vector3(2.5, 0.4 + i * 0.12, -0.8 + i * 0.14),
        ];
        const curve = new THREE.CatmullRomCurve3(points);
        const mesh = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 40, 0.015, 6, false),
          new THREE.MeshBasicMaterial({ color: colors[i % colors.length], transparent: true, opacity: 0.25 })
        );
        mesh.rotation.y = i * 0.6;
        lines.push(mesh);
      }
      return lines;
    }

    setState(state) {
      this.state = state;
    }

    handleResize() {
      if (!this.renderer || !this.camera || !this.host) {
        return;
      }
      const { clientWidth, clientHeight } = this.host;
      if (!clientWidth || !clientHeight) {
        return;
      }
      this.camera.aspect = clientWidth / clientHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(clientWidth, clientHeight, false);
    }

    startAnimation() {
      if (this.animationStarted) {
        return;
      }
      this.animationStarted = true;
      this.tick = this.tick.bind(this);
      this.tick();
    }

    tick() {
      if (!this.renderer || !this.scene || !this.camera) {
        return;
      }

      const time = performance.now() * 0.001;
      const stateIntensity = this.stateIntensity[this.state] || this.stateIntensity.idle;
      const motionFactor = reducedMotion ? 0.24 : 1;

      this.root.rotation.y = time * (0.22 * motionFactor) + 0.5;
      this.root.rotation.x = Math.sin(time * 0.8) * 0.2;

      if (this.core) {
        this.core.rotation.y = time * (0.45 * motionFactor) + 0.7;
        this.core.rotation.x = Math.sin(time * 1.1) * 0.25;
        this.core.scale.setScalar(1 + Math.sin(time * 2.1) * 0.08 + stateIntensity * 0.18);
      }

      if (this.halo) {
        this.halo.rotation.y = time * 0.5;
        this.halo.rotation.x = Math.sin(time * 0.9) * 0.4;
        this.halo.scale.setScalar(1 + Math.sin(time * 2.5) * 0.08 + stateIntensity * 0.4);
      }

      if (this.orbitGroup) {
        this.orbitGroup.rotation.y = time * (0.46 * motionFactor);
        this.orbitGroup.rotation.x = Math.cos(time * 0.7) * 0.3;
        this.lines.forEach((line, index) => {
          line.rotation.z = time * (0.35 + index * 0.08) * motionFactor;
          line.material.opacity = 0.17 + (0.16 * stateIntensity) + Math.sin(time * 2 + index) * 0.06;
        });
      }

      if (this.core && this.core.children && this.core.children.length > 0) {
        const scanMesh = this.core.children.find((child) => child.geometry && child.geometry.type === 'TorusGeometry' && child.scale && child.scale.x > 1.5);
        if (scanMesh) {
          scanMesh.rotation.z = time * 1.4;
        }
      }

      if (this.particles) {
        this.particles.rotation.y = time * (0.35 * motionFactor);
        this.particles.rotation.z = Math.sin(time * 0.6) * 0.2;
        this.particles.material.opacity = 0.42 + stateIntensity * 0.5;
      }

      if (this.pulseRings) {
        this.pulseRings.forEach((ring, index) => {
          const pulse = (Math.sin(time * (2.4 + index * 0.6) + index) + 1) * 0.5;
          ring.scale.setScalar(1 + (pulse * stateIntensity * 0.6) + index * 0.08);
          ring.material.opacity = 0.08 + (stateIntensity * 0.18) + pulse * 0.24;
          ring.rotation.z = time * (0.5 + index * 0.3);
        });
      }

      if (this.hudLines) {
        this.hudLines.forEach((line, index) => {
          line.rotation.z = time * (0.22 + index * 0.08);
          line.material.opacity = 0.12 + (stateIntensity * 0.26) + Math.sin(time * 2.2 + index) * 0.08;
        });
      }

      this.renderer.render(this.scene, this.camera);
      this.rafId = requestAnimationFrame(this.tick);
    }

    destroy() {
      if (this.rafId) {
        cancelAnimationFrame(this.rafId);
      }
      if (this.renderer) {
        this.renderer.dispose();
      }
      if (this.host) {
        this.host.innerHTML = '';
      }
      window.removeEventListener('resize', this.resizeHandler);
    }
  }

  try {
    const visualizer = new HolographicCore(container);
    visualizer.init();
    window.brainVisualizer = visualizer;
  } catch (error) {
    console.warn('WebGL indisponível; usando fallback visual do CAIO:', error);
    container.classList.add('brain-fallback');
    container.innerHTML = '<div class="brain-fallback-mark">CAIO</div>';
  }
})();
