package com.attendance.tokenhub.domain;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Repository;

@Repository
public class RevisionSequence {
    private final EntityManager entityManager;

    public RevisionSequence(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public long next() {
        Object value = entityManager.createNativeQuery("SELECT NEXTVAL('token_revision_seq')").getSingleResult();
        return ((Number) value).longValue();
    }
}
