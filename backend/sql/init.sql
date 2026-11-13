-- ============================================================
-- 待办清单 数据库初始化脚本（MySQL 8.0+）
-- 用法（Windows PowerShell / CMD，把 <root密码> 换成你自己的）：
--     mysql -u root -p"<root密码>" < backend\sql\init.sql
-- 用法（Linux 服务器上）：
--     mysql -u root -p < ./sql/init.sql
-- 说明：脚本可重复执行（IF NOT EXISTS），不会删除已有数据。
-- ============================================================

-- 1. 建库（utf8mb4 支持中文与 emoji）
CREATE DATABASE IF NOT EXISTS `todo_db`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

-- 2. 建业务账号（应用不要用 root 连库）
--    作用域用 '%'：本机 127.0.0.1 与容器内互相访问都能匹配，避免出现
--    'todo'@'localhost' 与 'todo'@'%' 两个账号密码不一致的坑。
--    Docker 场景下镜像入口会用 .env 里的 MYSQL_USER/MYSQL_PASSWORD 先建好同名账号，
--    这里的 IF NOT EXISTS 会自动跳过，以 .env 的密码为准。
--    生产环境请把 'todo_pass_123' 换成强密码，并同步修改 backend/.env 与 .env。
CREATE USER IF NOT EXISTS 'todo'@'%' IDENTIFIED BY 'todo_pass_123';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
    ON `todo_db`.* TO 'todo'@'%';
FLUSH PRIVILEGES;

USE `todo_db`;

-- 3. 待办主表
CREATE TABLE IF NOT EXISTS `todos` (
    `id`           INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `content`      VARCHAR(500) NOT NULL COMMENT '待办内容',
    `completed`    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '0=未完成 1=已完成',
    `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `completed_at` DATETIME     NULL DEFAULT NULL COMMENT '完成时间',
    PRIMARY KEY (`id`),
    KEY `idx_completed` (`completed`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='待办清单';

-- 4. 操作流水表（历史轨迹，可选展示）
CREATE TABLE IF NOT EXISTS `todo_logs` (
    `id`         INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `todo_id`    INT UNSIGNED NOT NULL COMMENT '关联待办 id',
    `action`     VARCHAR(20)  NOT NULL COMMENT 'create/update_content/complete/reopen/delete',
    `detail`     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '变更描述',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发生时间',
    PRIMARY KEY (`id`),
    KEY `idx_logs_todo_id` (`todo_id`),
    KEY `idx_logs_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='待办操作流水';

-- 5. 验证
SELECT '建库建表完成' AS result;
SHOW TABLES;
