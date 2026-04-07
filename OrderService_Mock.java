package com.wsa.platform.service;

import com.wsa.platform.model.Order;
import com.wsa.platform.repository.OrderRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @Autowired
    private OrderRepository orderRepository;

    public void createOrder(Order order) {
        // ❌ 違反 Single Responsibility Principle: 同時處理業務邏輯與日誌，且無驗證
        System.out.println("Creating order: " + order.getId());
        
        // ❌ 違反 Early Return: 這裡應該先檢查 null
        if (order != null) {
            if (order.getItems() != null && !order.getItems().isEmpty()) {
                orderRepository.save(order);
            }
        }
    }
}
