<template>
  <header class="app-header">
    <div class="inner">
      <h1 style="font-size:18px;padding:16px 0;">EFW-AI 智能投递助手</h1>
      <nav>
        <router-link to="/">看板</router-link>
        <router-link to="/applications">投递记录</router-link>
        <router-link to="/semi-queue">半自动清单</router-link>
        <router-link to="/chat">智能助手</router-link>
        <router-link to="/config">配置</router-link>
      </nav>
    </div>
  </header>
  <main>
    <LoginStatusBar />
    <router-view />
  </main>
</template>

<script setup>
import LoginStatusBar from './components/LoginStatusBar.vue'
</script>
