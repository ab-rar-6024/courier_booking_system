-- Run this in phpMyAdmin > SQL tab

CREATE DATABASE IF NOT EXISTS booking_system
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE booking_system;

-- Users
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL
);
INSERT IGNORE INTO users (username, password) VALUES ('admin','admin123');

-- Zones
CREATE TABLE IF NOT EXISTS zones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    district VARCHAR(100) NOT NULL,
    rate_zone VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rates
CREATE TABLE IF NOT EXISTS rates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    code_fullform VARCHAR(150) NOT NULL,
    place VARCHAR(100) NOT NULL,
    rate_250g DECIMAL(10,2) DEFAULT 0,
    rate_500g DECIMAL(10,2) DEFAULT 0,
    rate_500g_1 DECIMAL(10,2) DEFAULT 0,
    rate_1_to_3kg DECIMAL(10,2) DEFAULT 0,
    rate_3_to_10kg DECIMAL(10,2) DEFAULT 0,
    rate_above_10kg DECIMAL(10,2) DEFAULT 0,
    fuel DECIMAL(10,2) DEFAULT 0,
    INDEX idx_code (code),
    INDEX idx_place (place)
);

-- Bookings
CREATE TABLE IF NOT EXISTS bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(20) NOT NULL,
    booking_date DATE NOT NULL,
    awb_no VARCHAR(50),
    destination VARCHAR(100),
    weight DECIMAL(10,3) DEFAULT 0,
    courier VARCHAR(100),
    zone VARCHAR(100),
    auto_amount DECIMAL(10,2) DEFAULT 0,
    fuel DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2) DEFAULT 0,
    client_name VARCHAR(150),
    inv_no VARCHAR(50),
    inv_date VARCHAR(50),
    INDEX idx_code (code),
    INDEX idx_date (booking_date)
);

-- Day Wise
CREATE TABLE IF NOT EXISTS day_wise (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_date DATE NOT NULL,
    total_weight DECIMAL(10,3) DEFAULT 0,
    total_sales DECIMAL(10,2) DEFAULT 0
);

-- Sample data
INSERT IGNORE INTO zones (district, rate_zone) VALUES
  ('CHENNAI','Zone A'),('MADURAI','Zone B'),('COIMBATORE','Zone B'),
  ('MUMBAI','Zone C'),('DELHI','Zone C'),('HYDERABAD','Zone B');

INSERT IGNORE INTO rates (code,code_fullform,place,rate_250g,rate_500g,rate_500g_1,rate_1_to_3kg,rate_3_to_10kg,rate_above_10kg,fuel) VALUES
  ('MAS','M&S CONTAINER LINES PVT LTD','CHENNAI',20,20,15,30,25,20,0),
  ('MAS','M&S CONTAINER LINES PVT LTD','TAMIL NADU',25,25,20,35,30,25,0),
  ('MAS','M&S CONTAINER LINES PVT LTD','KERALA',30,30,25,50,45,40,0),
  ('MAS','M&S CONTAINER LINES PVT LTD','MUMBAI',60,60,60,120,120,120,0),
  ('RRT','RR TRADING COMPANY','HYDERABAD',35,35,25,50,40,35,0),
  ('RRT','RR TRADING COMPANY','MUMBAI',70,70,60,125,120,120,0),
  ('SFA','SAFETY FOR ALL','CHENNAI',20,20,15,30,25,20,0),
  ('SFA','SAFETY FOR ALL','KERALA',30,30,25,50,45,40,0);
