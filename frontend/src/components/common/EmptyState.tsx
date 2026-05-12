interface Props {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: Props) {
  return (
    <div className="text-center py-12 text-slate-500 border-2 border-dashed border-slate-200 rounded-lg">
      <p className="font-medium text-slate-700">{title}</p>
      {description && <p className="mt-2 text-sm">{description}</p>}
    </div>
  );
}
