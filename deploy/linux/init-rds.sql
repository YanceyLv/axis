-- Axis / TrendAI RDS initialization template.
-- Run this with the RDS administrator account.
-- Replace the password before executing.

CREATE DATABASE IF NOT EXISTS axis
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'axis_app'@'%' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
ON axis.*
TO 'axis_app'@'%';

FLUSH PRIVILEGES;
