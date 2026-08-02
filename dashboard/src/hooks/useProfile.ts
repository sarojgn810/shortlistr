"use client";

import { useState, useEffect, useCallback } from "react";
import { api, type ProfileSetup } from "@/src/lib/api/client";

export function useProfile() {
  const [profile, setProfile] = useState<ProfileSetup | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getProfile();
      setProfile(data);
    } catch {
      setError("Could not load profile — is the API running?");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const save = async (updates: Partial<ProfileSetup> & { llm_api_key?: string; target_titles?: string[] }) => {
    setIsSaving(true);
    try {
      const updated = await api.saveProfile(updates);
      setProfile(updated);
      return updated;
    } finally {
      setIsSaving(false);
    }
  };

  return { profile, isLoading, isSaving, error, refetch: fetch, save };
}
