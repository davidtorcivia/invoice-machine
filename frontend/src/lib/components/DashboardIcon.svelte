<script>
  import Icons from './Icons.svelte';
  export let size = 'md';
  export let class_ = '';
</script>

<Icons {size} class_={class_}>
  <rect width="7" height="9" x="3" y="3" rx="1" />
  <rect width="7" height="5" x="14" y="3" rx="1" />
  <rect width="7" height="9" x="14" y="12" rx="1" />
  <rect width="7" height="5" x="3" y="16" rx="1" />
</Icons>
