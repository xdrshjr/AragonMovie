'use strict';

const { Menu, shell, dialog, app } = require('electron');

/**
 * Minimal, product-grade application menu. Everything the support workflow
 * needs (re-run onboarding, jump to logs/data, API docs) is one click away.
 */
function buildMenu(ctx) {
  const isMac = process.platform === 'darwin';

  const template = [
    ...(isMac
      ? [
          {
            label: app.getName(),
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          },
        ]
      : []),
    {
      label: '应用',
      submenu: [
        {
          label: '重新运行初始配置…',
          accelerator: 'CmdOrCtrl+Shift+,',
          click: () => ctx.openWizard({ fromMenu: true }),
        },
        { type: 'separator' },
        {
          label: '打开数据目录',
          click: () => ctx.openPath('data'),
        },
        {
          label: '打开日志目录',
          click: () => ctx.openPath('logs'),
        },
        {
          label: '打开配置文件',
          click: () => ctx.openPath('settings'),
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit', label: '退出 AragonMovie' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '重新加载' },
        { role: 'forceReload', label: '强制重新加载' },
        { role: 'toggleDevTools', label: '开发者工具' },
        { type: 'separator' },
        { role: 'resetZoom', label: '实际大小' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
      ],
    },
    {
      label: '帮助',
      submenu: [
        {
          label: 'API 文档',
          click: () => {
            if (ctx.backendUrl()) shell.openExternal(`${ctx.backendUrl()}/docs`);
          },
        },
        {
          label: '关于 AragonMovie',
          click: () => {
            const info = ctx.info();
            dialog.showMessageBox({
              type: 'info',
              title: '关于 AragonMovie',
              message: `AragonMovie ${info.appVersion}`,
              detail: [
                `Electron ${info.electron} · Chromium ${info.chrome} · Node ${info.node}`,
                `本地后端：${info.apiBase || '未启动'}`,
                `界面服务：${info.webUrl || '未启动'}`,
                `数据目录：${info.userData}`,
                `日志：${info.logFile || info.logDir}`,
              ].join('\n'),
              buttons: ['好'],
              noLink: true,
            });
          },
        },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

function applyMenu(ctx) {
  Menu.setApplicationMenu(buildMenu(ctx));
}

module.exports = { buildMenu, applyMenu };
