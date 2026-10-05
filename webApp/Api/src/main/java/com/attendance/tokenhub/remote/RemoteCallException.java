package com.attendance.tokenhub.remote;

public class RemoteCallException extends RuntimeException {
    public RemoteCallException(String message) {
        super(message);
    }

    public RemoteCallException(String message, Throwable cause) {
        super(message, cause);
    }
}
