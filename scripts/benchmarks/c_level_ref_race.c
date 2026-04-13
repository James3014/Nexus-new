#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <pthread.h>
#include <unistd.h>
#include <stdbool.h>

typedef struct {
    _Atomic int refcount;
    _Atomic bool is_alive;
    int data;
    pthread_mutex_t lock; // 🧬 v23 硬化：細粒度同步鎖
} PyObject_Hardened;

PyObject_Hardened *global_obj = NULL;

void* thread_dealloc(void* arg) {
    PyObject_Hardened *obj = (PyObject_Hardened*)arg;
    
    // v23 Formal Fix: 析構與檢查必須互斥
    pthread_mutex_lock(&obj->lock);
    int old_refs = atomic_fetch_sub(&obj->refcount, 1);
    if (old_refs == 1) {
        atomic_store(&obj->is_alive, false);
        printf("💀 [Thread A] Object Deallocated safely within Atomic Window\n");
    }
    pthread_mutex_unlock(&obj->lock);
    return NULL;
}

void* thread_weakref_access(void* arg) {
    // v23 Formal Fix: 採用雙階段檢查協定
    if (global_obj) {
        pthread_mutex_lock(&global_obj->lock);
        if (atomic_load(&global_obj->is_alive)) {
            // 🛡️ 在鎖的保護下，此處訪問絕對安全
            printf("✅ [Thread B] Safe Access: %d\n", global_obj->data);
        } else {
            printf("🚫 [Thread B] Refused: Object is DEAD\n");
        }
        pthread_mutex_unlock(&global_obj->lock);
    }
    return NULL;
}

int main() {
    global_obj = malloc(sizeof(PyObject_Hardened));
    atomic_init(&global_obj->refcount, 1);
    atomic_init(&global_obj->is_alive, true);
    pthread_mutex_init(&global_obj->lock, NULL);
    global_obj->data = 42;

    pthread_t t1, t2;
    printf("🚀 [v23 C-Level Fix] Validating Atomic Window Protocol...\n");
    
    pthread_create(&t2, NULL, thread_weakref_access, NULL);
    pthread_create(&t1, NULL, thread_dealloc, global_obj);

    pthread_join(t1, NULL);
    pthread_join(t2, NULL);

    pthread_mutex_destroy(&global_obj->lock);
    free(global_obj);
    return 0;
}
