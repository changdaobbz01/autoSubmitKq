package com.attendance.tokenhub.domain;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface TokenCredentialRepository extends JpaRepository<TokenCredential, String> {
    List<TokenCredential> findByRevisionGreaterThanOrderByRevisionAsc(long revision, Pageable pageable);
    List<TokenCredential> findAllByOrderByUpdatedAtDesc(Pageable pageable);

    @Query("select coalesce(max(item.revision), 0) from TokenCredential item")
    long findLatestRevision();
}
