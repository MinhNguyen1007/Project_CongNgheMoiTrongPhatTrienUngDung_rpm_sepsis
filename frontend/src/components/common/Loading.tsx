interface Props {
  message?: string;
}

export function Loading({ message = "Loading..." }: Props) {
  return (
    <div className="flex items-center justify-center py-12 text-slate-500">
      <div className="animate-spin h-5 w-5 border-2 border-slate-300 border-t-blue-600 rounded-full mr-3" />
      <span>{message}</span>
    </div>
  );
}
