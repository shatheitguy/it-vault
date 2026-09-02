-- IT Guy - The Assets Manager schema (MariaDB 11)
CREATE TABLE IF NOT EXISTS `Assets` (
    `_id` VARCHAR(40) PRIMARY KEY,
    `Name` VARCHAR(255),
    `Type` VARCHAR(255),
    `Serial` VARCHAR(255),
    `Location` VARCHAR(255),
    `Status` VARCHAR(255),
    `AssignedTo` VARCHAR(255),
    `Notes` TEXT,
    `PurchaseDate` VARCHAR(255),
    INDEX `idx_serial` (`Serial`),
    INDEX `idx_status` (`Status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `Users` (
    `username` VARCHAR(50) PRIMARY KEY,
    `password` VARCHAR(100),
    `role` VARCHAR(20),
    `display` VARCHAR(80),
    INDEX `idx_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Seed admin (password: admin123). Replace or change after first login.
SET @salt = 'initseed0';
INSERT IGNORE INTO `Users` (`username`, `password`, `role`, `display`)
VALUES ('admin', CONCAT(@salt, '$', SHA2(CONCAT(@salt, 'admin123'), 256)), 'admin', 'Administrator');
