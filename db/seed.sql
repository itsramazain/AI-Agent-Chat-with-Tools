INSERT OR IGNORE INTO books(isbn, title, author, stock, price) VALUES
('9780132350884', 'Clean Code', 'Robert C. Martin', 12, 39.99),
('9780134494166', 'Clean Architecture', 'Robert C. Martin', 7, 41.00),
('9780201616224', 'The Pragmatic Programmer', 'Andrew Hunt', 5, 42.00),
('9780131103627', 'The C Programming Language', 'Brian W. Kernighan', 4, 35.50),
('9781492056355', 'Designing Data-Intensive Applications', 'Martin Kleppmann', 3, 49.00),
('9780262033848', 'Introduction to Algorithms', 'Thomas H. Cormen', 2, 85.00),
('9780134685991', 'Effective Java', 'Joshua Bloch', 6, 45.00),
('9780596007126', 'Head First Design Patterns', 'Eric Freeman', 5, 38.00),
('9780135974445', 'Refactoring', 'Martin Fowler', 4, 47.00),
('9781617296086', 'Spring in Action', 'Craig Walls', 6, 44.00);


INSERT OR IGNORE INTO customers(id, name, email) VALUES
(1, 'Rama', 'rama@example.com'),
(2, 'Oduai', 'oduai@example.com'),
(3, 'Laila', 'laila@example.com');


INSERT OR IGNORE INTO orders(id, customer_id, status) VALUES
(1, 1, 'created'),
(2, 2, 'fulfilled'),
(3, 3, 'created');

INSERT OR IGNORE INTO order_items(order_id, isbn, qty, unit_price) VALUES
(1, '9780132350884', 1, 39.99),
(2, '9780201616224', 2, 42.00),
(2, '9780134685991', 1, 45.00),
(3, '9780262033848', 1, 85.00);
