import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/authStore";
import type { UserResponse, UserRole } from "@/types/api";

const roleTone: Record<UserRole, string> = {
  admin: "bg-amber-100 text-amber-800 ring-amber-200",
  doctor: "bg-sky-100 text-sky-800 ring-sky-200",
  viewer: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function AdminSettings() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.username);

  const {
    data: users = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["users"],
    queryFn: api.listUsers,
  });

  const registerMutation = useMutation({
    mutationFn: api.registerUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      patch,
    }: {
      id: number;
      patch: Parameters<typeof api.updateUser>[1];
    }) => api.updateUser(id, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-800">
          Quản trị người dùng
        </h2>
        <span className="text-xs text-slate-500">
          Chỉ admin truy cập được trang này.
        </span>
      </div>

      <CreateUserForm
        pending={registerMutation.isPending}
        error={registerMutation.error?.message}
        onSubmit={(payload) => registerMutation.mutate(payload)}
      />

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-2 text-sm font-medium text-slate-700">
          Danh sách ({users.length})
        </div>
        {isLoading && (
          <div className="px-4 py-6 text-sm text-slate-500">Đang tải...</div>
        )}
        {isError && (
          <div className="px-4 py-6 text-sm text-red-600">
            Lỗi: {error instanceof Error ? error.message : "unknown"}
          </div>
        )}
        {!isLoading && !isError && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 text-left">ID</th>
                <th className="px-4 py-2 text-left">Username</th>
                <th className="px-4 py-2 text-left">Họ tên</th>
                <th className="px-4 py-2 text-left">Role</th>
                <th className="px-4 py-2 text-left">Active</th>
                <th className="px-4 py-2 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  isSelf={u.username === currentUser}
                  onChangeRole={(role) =>
                    updateMutation.mutate({ id: u.id, patch: { role } })
                  }
                  onToggleActive={() =>
                    updateMutation.mutate({
                      id: u.id,
                      patch: { is_active: !u.is_active },
                    })
                  }
                  onDelete={() => {
                    if (confirm(`Xoá user "${u.username}"?`))
                      deleteMutation.mutate(u.id);
                  }}
                  busy={updateMutation.isPending || deleteMutation.isPending}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── sub-components ──────────────────────────────────────

interface CreateUserFormProps {
  pending: boolean;
  error?: string;
  onSubmit: (payload: {
    username: string;
    password: string;
    full_name: string;
    role: UserRole;
  }) => void;
}

function CreateUserForm({ pending, error, onSubmit }: CreateUserFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");

  const handle = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ username, password, full_name: fullName, role });
    if (!error) {
      setUsername("");
      setPassword("");
      setFullName("");
      setRole("viewer");
    }
  };

  return (
    <form
      onSubmit={handle}
      className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-5"
    >
      <input
        className="rounded border border-slate-300 px-3 py-2 text-sm"
        placeholder="username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        minLength={3}
        required
      />
      <input
        className="rounded border border-slate-300 px-3 py-2 text-sm"
        placeholder="password (>=6)"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={6}
        required
      />
      <input
        className="rounded border border-slate-300 px-3 py-2 text-sm"
        placeholder="Họ tên (tuỳ chọn)"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
      />
      <select
        className="rounded border border-slate-300 px-3 py-2 text-sm"
        value={role}
        onChange={(e) => setRole(e.target.value as UserRole)}
      >
        <option value="viewer">viewer</option>
        <option value="doctor">doctor</option>
        <option value="admin">admin</option>
      </select>
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
      >
        {pending ? "Đang tạo..." : "+ Tạo user"}
      </button>
      {error && (
        <div className="md:col-span-5 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
    </form>
  );
}

interface UserRowProps {
  user: UserResponse;
  isSelf: boolean;
  busy: boolean;
  onChangeRole: (role: UserRole) => void;
  onToggleActive: () => void;
  onDelete: () => void;
}

function UserRow({
  user,
  isSelf,
  busy,
  onChangeRole,
  onToggleActive,
  onDelete,
}: UserRowProps) {
  return (
    <tr className="border-t border-slate-100">
      <td className="px-4 py-2 text-slate-500">{user.id}</td>
      <td className="px-4 py-2 font-medium text-slate-800">
        {user.username}
        {isSelf && <span className="ml-1 text-xs text-slate-400">(bạn)</span>}
      </td>
      <td className="px-4 py-2 text-slate-600">{user.full_name || "—"}</td>
      <td className="px-4 py-2">
        <select
          value={user.role}
          disabled={isSelf || busy}
          onChange={(e) => onChangeRole(e.target.value as UserRole)}
          className={`rounded px-2 py-1 text-xs font-medium ring-1 ring-inset ${roleTone[user.role]} disabled:opacity-60`}
        >
          <option value="viewer">viewer</option>
          <option value="doctor">doctor</option>
          <option value="admin">admin</option>
        </select>
      </td>
      <td className="px-4 py-2">
        <button
          onClick={onToggleActive}
          disabled={isSelf || busy}
          className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${
            user.is_active
              ? "bg-emerald-100 text-emerald-800 ring-emerald-200"
              : "bg-slate-100 text-slate-500 ring-slate-200"
          } disabled:opacity-60`}
        >
          {user.is_active ? "active" : "disabled"}
        </button>
      </td>
      <td className="px-4 py-2 text-right">
        <button
          onClick={onDelete}
          disabled={isSelf || busy}
          className="rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-40"
        >
          Xoá
        </button>
      </td>
    </tr>
  );
}
