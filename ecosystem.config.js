module.exports = {
  apps: [{
    name: 'hypertracker-bot',
    script: 'venv/bin/python',
    args: 'run.py',
    cwd: '/home/ubuntu/hypertracker-bot',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_file: './logs/combined.log',
    time: true
  }]
};
