<template>
  <nav class="sidebar">
    <div class="brand">Agent Router</div>
    <router-link to="/" class="nav-item" active-class="active">
      <span class="icon">📊</span>
      <span>仪表盘</span>
    </router-link>
    <router-link to="/config" class="nav-item" active-class="active">
      <span class="icon">⚙️</span>
      <span>配置管理</span>
    </router-link>
  </nav>
</template>

<style scoped>
.sidebar {
  position: fixed; left: 0; top: 0; bottom: 0;
  width: 200px;
  background: #1e1e2e;
  border-right: 1px solid #313244;
  padding: 16px 0;
  z-index: 10;
}
.brand {
  color: #cdd6f4; font-size: 16px; font-weight: 700;
  padding: 0 16px 16px;
  border-bottom: 1px solid #313244;
  margin-bottom: 8px;
}
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px;
  color: #a6adc8;
  text-decoration: none;
  font-size: 14px;
  transition: background 0.15s;
}
.nav-item:hover { background: #313244; color: #cdd6f4; }
.nav-item.active { background: #313244; color: #89b4fa; border-right: 2px solid #89b4fa; }
.icon { font-size: 16px; }
</style>
